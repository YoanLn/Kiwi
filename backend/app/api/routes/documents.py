from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import logging

from app.core.database import get_db
from app.core.config import settings
from app.core.auth import get_current_user_optional, User
from app.models.document import Document, DocumentType, VerificationStatus
from app.models.claim import Claim, ClaimStatus
from app.schemas.document import DocumentResponse
from app.services.document_verification import DocumentVerificationService
from app.services.storage_service import StorageService
from app.services.vertex_search_service import VertexSearchService

router = APIRouter()
logger = logging.getLogger(__name__)


async def _index_document_in_vertex_search(
    document_id: int,
    claim_id: int,
    user_id: str,
    file_path: str,
    document_type: str,
    filename: str,
    mime_type: str
):
    """Background task to index document in Vertex AI Search."""
    if not settings.ENABLE_VERTEX_SEARCH or not settings.ENABLE_DOCUMENT_INDEXING:
        return

    try:
        search_service = VertexSearchService()

        # Build GCS URI from file path
        gcs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{file_path}"

        result = await search_service.index_document(
            document_id=document_id,
            claim_id=claim_id,
            user_id=user_id,
            gcs_uri=gcs_uri,
            document_type=document_type,
            filename=filename,
            mime_type=mime_type
        )

        if result["success"]:
            logger.info(f"Document {document_id} indexed in Vertex AI Search: {result['document_id']}")
        else:
            logger.error(f"Failed to index document {document_id}: {result.get('error')}")

    except Exception as e:
        logger.error(f"Error indexing document {document_id} in Vertex AI Search: {str(e)}")


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    claim_id: int = Form(...),
    document_type: str = Form(...),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Upload, verify, and index a document for a claim.

    Demo mode: allows unauthenticated access and derives user_id from the claim.
    For production, require JWT auth and keep strict ownership checks.
    """
    # Verify claim exists
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim not found"
        )

    if not settings.DEMO_MODE and current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # SECURITY: Get user_id from auth token when available; fallback in demo
    user_id = current_user.user_id if current_user else settings.DEMO_USER_ID

    # SECURITY: Verify user owns this claim when authenticated
    if current_user and claim.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to upload documents to this claim"
        )

    # Validate document type
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type. Must be one of: {[e.value for e in DocumentType]}"
        )

    # Upload file to GCS
    storage_service = StorageService()
    file_content = await file.read()
    file_path = await storage_service.upload_file(
        file_content,
        file.filename,
        claim_id
    )

    # Create document record
    document = Document(
        claim_id=claim_id,
        document_type=doc_type,
        filename=file.filename,
        file_path=file_path,
        file_size=len(file_content),
        mime_type=file.content_type,
        verification_status=VerificationStatus.PENDING
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    # Trigger AI verification (demo mode only affects auth, not validation)
    verification_service = DocumentVerificationService()
    verification_result = await verification_service.verify_document(
        file_content,
        doc_type,
        file.content_type,
        document_id=document.id,
        filename=file.filename,
    )

    # Update document with verification results
    document.verification_status = verification_result["status"]
    document.ai_analysis = verification_result["analysis"]
    document.confidence_score = verification_result["confidence_score"]
    document.is_compliant = verification_result["is_compliant"]
    document.compliance_issues = verification_result.get("compliance_issues")
    document.verified_at = datetime.utcnow()

    # Update claim status based on document verification
    if verification_result["is_compliant"]:
        claim.status = ClaimStatus.UNDER_REVIEW
        claim.status_message = "Documents received and verified. Claim is under review."
    else:
        claim.status = ClaimStatus.ADDITIONAL_INFO_REQUIRED
        claim.status_message = f"Document verification issues: {verification_result.get('compliance_issues')}"

    db.commit()
    db.refresh(document)

    # Index document in Vertex AI Search (background task)
    # Only index compliant documents to avoid polluting the search index
    if verification_result.get("should_index"):
        background_tasks.add_task(
            _index_document_in_vertex_search,
            document_id=document.id,
            claim_id=claim_id,
            user_id=user_id,
            file_path=file_path,
            document_type=doc_type.value,
            filename=file.filename,
            mime_type=file.content_type
        )

    return document


@router.get("/claim/{claim_id}", response_model=List[DocumentResponse])
async def get_claim_documents(claim_id: int, db: Session = Depends(get_db)):
    """Get all documents for a specific claim"""
    documents = db.query(Document).filter(Document.claim_id == claim_id).all()
    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document details by ID"""
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Delete a document from storage, database, and search index"""
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    claim_id = document.claim_id

    # Delete from storage
    storage_service = StorageService()
    await storage_service.delete_file(document.file_path)

    # Delete from Vertex AI Search index (background task)
    if settings.ENABLE_VERTEX_SEARCH:
        async def _delete_from_search():
            try:
                search_service = VertexSearchService()
                result = await search_service.delete_document(claim_id, document_id)
                if result["success"]:
                    logger.info(f"Document {document_id} removed from Vertex AI Search")
                else:
                    logger.warning(f"Failed to remove document {document_id} from search: {result.get('error')}")
            except Exception as e:
                logger.error(f"Error removing document {document_id} from search: {str(e)}")

        background_tasks.add_task(_delete_from_search)

    # Delete from database
    db.delete(document)
    db.commit()

    return None
