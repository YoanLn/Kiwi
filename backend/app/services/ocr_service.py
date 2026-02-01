"""
OCR Service using Gemini (Vertex AI).
"""
import asyncio
import logging
import re
import time
from io import BytesIO
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict, Any, List

import vertexai
from vertexai.generative_models import GenerativeModel, Part
from PyPDF2 import PdfReader

from app.core.config import settings
from app.schemas.validation import OCRResult
from app.models.document import DocumentType

logger = logging.getLogger(__name__)

DOCUMENT_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

IMAGE_MIME_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
}

MARKDOWN_TABLE_RE = re.compile(
    r"(?:^|\n)(\|.+\|\n\|[-:| ]+\|\n(?:\|.*\|\n?)*)",
    re.MULTILINE,
)


class OCRService:
    """Service for OCR processing using Gemini via Vertex AI."""

    def __init__(self):
        vertexai.init(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.VERTEX_AI_LOCATION,
        )
        self.model = GenerativeModel(settings.VERTEX_AI_MODEL_VISION)
        logger.info("OCR Service initialized with Gemini via Vertex AI")

    async def process_document(
        self,
        file_path: str,
        document_id: str,
        include_tables: bool = True,
        include_images: bool = False,
    ) -> OCRResult:
        """Process a document using Gemini OCR."""
        start_time = time.time()

        try:
            path = Path(file_path)
            extension = path.suffix.lower()

            if extension in DOCUMENT_MIME_TYPES:
                result = await self._process_document_file(
                    file_path, include_tables, include_images
                )
            elif extension in IMAGE_MIME_TYPES:
                result = await self._process_image_file(
                    file_path, include_tables, include_images
                )
            else:
                raise ValueError(f"Unsupported file type: {extension}")

            processing_time = time.time() - start_time

            return OCRResult(
                document_id=document_id,
                raw_text=result["raw_text"],
                structured_data=result.get("structured_data"),
                tables=result.get("tables"),
                images=result.get("images"),
                confidence=result.get("confidence"),
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            raise

    async def process_document_bytes(
        self,
        file_content: bytes,
        filename: str,
        document_id: str,
        mime_type: str,
        include_tables: bool = True,
        include_images: bool = False,
    ) -> OCRResult:
        """Process document from bytes content."""
        start_time = time.time()

        try:
            extension = Path(filename).suffix.lower()

            if extension in DOCUMENT_MIME_TYPES:
                mime_type = mime_type or DOCUMENT_MIME_TYPES.get(extension, 'application/pdf')
                result = await self._process_document_bytes(
                    file_content, mime_type, include_tables, include_images
                )
            elif extension in IMAGE_MIME_TYPES:
                mime_type = mime_type or IMAGE_MIME_TYPES.get(extension, 'image/png')
                result = await self._process_image_bytes(
                    file_content, mime_type, include_tables, include_images
                )
            else:
                raise ValueError(f"Unsupported file type: {extension}")

            processing_time = time.time() - start_time

            return OCRResult(
                document_id=document_id,
                raw_text=result["raw_text"],
                structured_data=result.get("structured_data"),
                tables=result.get("tables"),
                images=result.get("images"),
                confidence=result.get("confidence"),
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            raise

    async def _process_document_file(
        self,
        file_path: str,
        include_tables: bool,
        include_images: bool,
    ) -> Dict[str, Any]:
        """Process PDF/DOCX/PPTX files."""
        with open(file_path, "rb") as f:
            file_content = f.read()

        extension = Path(file_path).suffix.lower()
        mime_type = DOCUMENT_MIME_TYPES.get(extension, 'application/pdf')

        return await self._process_document_bytes(
            file_content, mime_type, include_tables, include_images
        )

    async def _process_document_bytes(
        self,
        file_content: bytes,
        mime_type: str,
        include_tables: bool,
        include_images: bool,
    ) -> Dict[str, Any]:
        """Process document bytes."""
        return await self._process_with_gemini(
            file_content=file_content,
            mime_type=mime_type,
            include_tables=include_tables,
            include_images=include_images,
        )

    async def _process_image_file(
        self,
        file_path: str,
        include_tables: bool,
        include_images: bool,
    ) -> Dict[str, Any]:
        """Process image files."""
        with open(file_path, "rb") as f:
            image_content = f.read()

        extension = Path(file_path).suffix.lower()
        mime_type = IMAGE_MIME_TYPES.get(extension, 'image/png')

        return await self._process_image_bytes(
            image_content, mime_type, include_tables, include_images
        )

    async def _process_image_bytes(
        self,
        image_content: bytes,
        mime_type: str,
        include_tables: bool,
        include_images: bool,
    ) -> Dict[str, Any]:
        """Process image bytes."""
        return await self._process_with_gemini(
            file_content=image_content,
            mime_type=mime_type,
            include_tables=include_tables,
            include_images=include_images,
        )

    async def _process_with_gemini(
        self,
        file_content: bytes,
        mime_type: str,
        include_tables: bool,
        include_images: bool,
    ) -> Dict[str, Any]:
        """Run Gemini OCR and normalize the response."""
        prompt = self._build_prompt(include_tables=include_tables)
        mime_type = mime_type or "application/octet-stream"

        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                [
                    prompt,
                    Part.from_data(data=file_content, mime_type=mime_type),
                ],
                generation_config={
                    "temperature": 0.0,
                    "max_output_tokens": 4096,
                    "top_p": 0.8,
                },
            )
        except Exception as exc:
            logger.error("Gemini OCR request failed: %s", exc)
            raise

        raw_text = (response.text or "").strip()
        if not raw_text:
            raw_text = "[No text content extracted from document]"

        tables = None
        if include_tables:
            tables = self._extract_markdown_tables(raw_text)
        if include_images:
            logger.debug("Gemini OCR does not return embedded image data; include_images ignored.")

        page_count = self._estimate_page_count(file_content, mime_type)

        return {
            "raw_text": raw_text,
            "tables": tables if tables else None,
            "images": None,
            "structured_data": {
                "page_count": page_count,
                "has_tables": bool(tables),
                "has_images": False,
            },
            "confidence": None,
        }

    def _build_prompt(self, include_tables: bool) -> str:
        """Build OCR prompt for Gemini."""
        lines = [
            "You are an OCR engine. Extract all readable text from the provided file.",
            "Return only the extracted text. Do not add commentary or summaries.",
            "Preserve line breaks and headings when possible.",
            "Do not describe images or layout elements; only transcribe text.",
        ]
        if include_tables:
            lines.append("If tables are present, reproduce them as Markdown tables.")
        else:
            lines.append("If tables are present, transcribe their text in reading order.")
        lines.append("If no text is found, return: [No text content extracted from document]")
        return "\n".join(lines)

    def _extract_markdown_tables(self, text: str) -> List[Dict[str, Any]]:
        """Extract Markdown table blocks into the expected response format."""
        if not text:
            return []

        tables: List[Dict[str, Any]] = []
        for match in MARKDOWN_TABLE_RE.finditer(text):
            table_text = match.group(1).strip()
            if table_text:
                tables.append(
                    {
                        "page_index": 0,
                        "content": table_text,
                    }
                )
        return tables

    def _estimate_page_count(self, file_content: bytes, mime_type: str) -> Optional[int]:
        """Estimate page count for PDFs; return 1 for images when possible."""
        if "pdf" in (mime_type or ""):
            try:
                reader = PdfReader(BytesIO(file_content))
                return len(reader.pages)
            except Exception:
                return None

        if mime_type.startswith("image/"):
            return 1

        return None

    def detect_document_type(self, ocr_text: str) -> DocumentType:
        """Detect the type of document based on OCR text."""
        text_lower = ocr_text.lower()

        # Insurance Policy
        if any(word in text_lower for word in ['policy number', 'numéro de police', 'insurance policy',
                                                'police d\'assurance', 'coverage', 'couverture', 'premium']):
            return DocumentType.INSURANCE_POLICY

        # Claim Form
        elif any(word in text_lower for word in ['claim form', 'formulaire de réclamation', 'claim number',
                                                  'numéro de sinistre', 'declaration of loss']):
            return DocumentType.CLAIM_FORM

        # Incident Report
        elif any(word in text_lower for word in ['police report', 'rapport de police', 'accident report',
                                                  'constat', 'incident report', 'procès-verbal']):
            return DocumentType.INCIDENT_REPORT

        # Proof of Ownership
        elif any(word in text_lower for word in ['proof of ownership', 'preuve de propriété', 'purchase receipt',
                                                  'bill of sale', 'acte de vente', 'ownership certificate']):
            return DocumentType.PROOF_OF_OWNERSHIP

        # Repair Estimate
        elif any(word in text_lower for word in ['repair estimate', 'devis de réparation', 'repair invoice',
                                                  'facture de réparation', 'estimate', 'devis']):
            return DocumentType.REPAIR_ESTIMATE

        # Medical Report
        elif any(word in text_lower for word in ['medical report', 'rapport médical', 'diagnosis', 'diagnostic',
                                                  'patient', 'doctor', 'médecin', 'hospital', 'hôpital',
                                                  'medical bill', 'facture médicale']):
            return DocumentType.MEDICAL_REPORT

        # ID Document
        elif any(word in text_lower for word in ['passport', 'passeport', 'identity card', 'carte d\'identité',
                                                  'driver license', 'permis de conduire', 'national id',
                                                  'république française', 'carte nationale']):
            return DocumentType.ID_DOCUMENT

        # Bank Details
        elif any(word in text_lower for word in ['bank details', 'coordonnées bancaires', 'iban', 'bic',
                                                  'account number', 'numéro de compte', 'bank account', 'rib']):
            return DocumentType.BANK_DETAILS

        # Evidence of Damage
        elif any(word in text_lower for word in ['damage', 'dommage', 'loss', 'perte', 'photo', 'evidence']):
            return DocumentType.EVIDENCE_OF_DAMAGE

        # Default to unrelated
        else:
            return DocumentType.UNRELATED


@lru_cache()
def get_ocr_service() -> OCRService:
    """Get cached OCR service instance."""
    return OCRService()
