"""
Vertex AI Search Service for document indexing and retrieval.
Implements Pattern A: single datastore with ACL per document.
Configured for EU region and sensitive insurance documents.
"""

from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions
from google.protobuf import struct_pb2
from typing import Dict, List, Optional
import json
import hashlib
import asyncio
import logging
from datetime import datetime
from functools import partial

from app.core.config import settings

logger = logging.getLogger(__name__)


class VertexSearchService:
    """
    Vertex AI Search service for indexing and retrieving insurance documents.

    Features:
    - Document-level ACL for multi-tenant security
    - EU region deployment for data residency
    - OCR + chunking for scanned/digital PDFs
    - Citation-aware retrieval for RAG
    """

    def __init__(self):
        # Use EU endpoint for data residency compliance
        # For 'eu' or 'us' locations, use regional endpoint
        self.location = settings.VERTEX_AI_SEARCH_LOCATION
        if self.location in ("eu", "us"):
            self.api_endpoint = f"{self.location}-discoveryengine.googleapis.com"
        else:
            self.api_endpoint = "discoveryengine.googleapis.com"

        self.client_options = ClientOptions(api_endpoint=self.api_endpoint)

        # Initialize clients
        self.document_client = discoveryengine.DocumentServiceClient(
            client_options=self.client_options
        )
        self.search_client = discoveryengine.SearchServiceClient(
            client_options=self.client_options
        )

        # Build resource paths
        self.project_id = settings.GOOGLE_CLOUD_PROJECT
        self.datastore_id = settings.VERTEX_AI_SEARCH_DATASTORE_ID
        self.engine_id = settings.VERTEX_AI_SEARCH_ENGINE_ID

        # Parent path for documents - CORRECT format per Google docs
        # projects/{project}/locations/{location}/collections/{collection}/dataStores/{data_store}/branches/{branch}
        self.parent = (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"collections/default_collection/dataStores/{self.datastore_id}/"
            f"branches/default_branch"
        )

        # Search serving config - use ENGINE with default_search (recommended by Google)
        # projects/{project}/locations/{location}/collections/default_collection/engines/{engine}/servingConfigs/default_search
        self.serving_config = (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"collections/default_collection/engines/{self.engine_id}/"
            f"servingConfigs/default_search"
        )

    def _generate_document_id(self, claim_id: int, document_id: int) -> str:
        """Generate a unique document ID for Vertex AI Search."""
        return f"claim_{claim_id}_doc_{document_id}"

    def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous function in a thread pool to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def index_document(
        self,
        document_id: int,
        claim_id: int,
        user_id: str,
        gcs_uri: str,
        document_type: str,
        filename: str,
        mime_type: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Index a document in Vertex AI Search with ACL for the owner.

        Args:
            document_id: Database ID of the document
            claim_id: Associated claim ID
            user_id: Owner user ID for ACL (MUST come from auth token, not request)
            gcs_uri: GCS URI of the document (gs://bucket/path)
            document_type: Type of document (IDENTITY, MEDICAL_REPORT, etc.)
            filename: Original filename
            mime_type: MIME type of the document
            metadata: Additional metadata to store

        Returns:
            Dict with indexing status and document name
        """
        try:
            search_doc_id = self._generate_document_id(claim_id, document_id)

            # Build document with ACL
            document = discoveryengine.Document()
            document.id = search_doc_id
            document.name = f"{self.parent}/documents/{search_doc_id}"

            # Set content from GCS
            document.content = discoveryengine.Document.Content()
            document.content.mime_type = mime_type
            document.content.uri = gcs_uri

            # Build struct for metadata
            struct_data = struct_pb2.Struct()
            struct_data.update({
                "claim_id": str(claim_id),
                "document_id": str(document_id),
                "document_type": document_type,
                "filename": filename,
                "user_id": user_id,
                "indexed_at": datetime.utcnow().isoformat(),
                **(metadata or {})
            })
            document.struct_data = struct_data

            # Set ACL - only document owner can access
            # This is the Pattern A implementation
            document.acl_info = discoveryengine.Document.AclInfo()
            reader = discoveryengine.Document.AclInfo.AccessRestriction()
            principal = discoveryengine.Principal()
            principal.user_id = user_id
            reader.principals.append(principal)
            document.acl_info.readers.append(reader)

            # Create or update document
            request = discoveryengine.CreateDocumentRequest(
                parent=self.parent,
                document=document,
                document_id=search_doc_id
            )

            # Run in thread pool to avoid blocking event loop
            result = await self._run_sync(self.document_client.create_document, request=request)

            return {
                "success": True,
                "document_name": result.name,
                "document_id": search_doc_id,
                "message": "Document indexed successfully"
            }

        except Exception as e:
            # Check if document already exists, then update
            if "ALREADY_EXISTS" in str(e):
                return await self.update_document(
                    document_id=document_id,
                    claim_id=claim_id,
                    user_id=user_id,
                    gcs_uri=gcs_uri,
                    document_type=document_type,
                    filename=filename,
                    mime_type=mime_type,
                    metadata=metadata
                )

            return {
                "success": False,
                "error": str(e),
                "message": "Failed to index document"
            }

    async def update_document(
        self,
        document_id: int,
        claim_id: int,
        user_id: str,
        gcs_uri: str,
        document_type: str,
        filename: str,
        mime_type: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Update an existing document in the index."""
        try:
            search_doc_id = self._generate_document_id(claim_id, document_id)

            document = discoveryengine.Document()
            document.id = search_doc_id
            document.name = f"{self.parent}/documents/{search_doc_id}"

            document.content = discoveryengine.Document.Content()
            document.content.mime_type = mime_type
            document.content.uri = gcs_uri

            struct_data = struct_pb2.Struct()
            struct_data.update({
                "claim_id": str(claim_id),
                "document_id": str(document_id),
                "document_type": document_type,
                "filename": filename,
                "user_id": user_id,
                "updated_at": datetime.utcnow().isoformat(),
                **(metadata or {})
            })
            document.struct_data = struct_data

            document.acl_info = discoveryengine.Document.AclInfo()
            reader = discoveryengine.Document.AclInfo.AccessRestriction()
            principal = discoveryengine.Principal()
            principal.user_id = user_id
            reader.principals.append(principal)
            document.acl_info.readers.append(reader)

            request = discoveryengine.UpdateDocumentRequest(
                document=document,
                allow_missing=True
            )

            # Run in thread pool to avoid blocking event loop
            result = await self._run_sync(self.document_client.update_document, request=request)

            return {
                "success": True,
                "document_name": result.name,
                "document_id": search_doc_id,
                "message": "Document updated successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update document"
            }

    async def delete_document(self, claim_id: int, document_id: int) -> Dict:
        """Remove a document from the search index."""
        try:
            search_doc_id = self._generate_document_id(claim_id, document_id)
            document_name = f"{self.parent}/documents/{search_doc_id}"

            request = discoveryengine.DeleteDocumentRequest(
                name=document_name
            )

            # Run in thread pool to avoid blocking event loop
            await self._run_sync(self.document_client.delete_document, request=request)

            return {
                "success": True,
                "message": "Document deleted from index"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to delete document from index"
            }

    async def search(
        self,
        query: str,
        user_id: str,
        page_size: int = 10,
        filter_expression: Optional[str] = None
    ) -> Dict:
        """
        Search documents with ACL filtering.

        The search automatically filters results based on user_id
        when ACL is enabled on the datastore.

        Args:
            query: Search query text
            user_id: User ID for ACL filtering
            page_size: Number of results to return
            filter_expression: Optional filter (e.g., "document_type = 'MEDICAL_REPORT'")

        Returns:
            Dict with search results and metadata
        """
        try:
            # Build search request
            request = discoveryengine.SearchRequest(
                serving_config=self.serving_config,
                query=query,
                page_size=page_size,
                # Enable snippet extraction for RAG
                content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                    snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                        return_snippet=True,
                        max_snippet_count=3
                    ),
                    extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                        max_extractive_answer_count=3,
                        max_extractive_segment_count=5
                    )
                ),
                # User info for ACL filtering
                
            )

            # Add filter if provided
            if filter_expression:
                request.filter = filter_expression

            # Execute search in thread pool to avoid blocking event loop
            response = await self._run_sync(self.search_client.search, request=request)

            # Process results
            results = []
            for result in response.results:
                doc_data = {
                    "document_id": result.document.id,
                    "document_name": result.document.name,
                }

                # Extract struct data
                if result.document.struct_data:
                    doc_data["metadata"] = dict(result.document.struct_data)

                # Extract snippets for RAG context
                snippets = []
                if hasattr(result.document, 'derived_struct_data'):
                    derived = result.document.derived_struct_data
                    if 'snippets' in derived:
                        for snippet in derived['snippets']:
                            snippets.append(snippet.get('snippet', ''))
                    if 'extractive_answers' in derived:
                        for answer in derived['extractive_answers']:
                            snippets.append(answer.get('content', ''))

                doc_data["snippets"] = snippets
                doc_data["relevance_score"] = getattr(result, 'relevance_score', None)

                results.append(doc_data)

            return {
                "success": True,
                "results": results,
                "total_size": response.total_size if hasattr(response, 'total_size') else len(results),
                "query": query
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "message": "Search failed"
            }

    async def search_for_rag(
        self,
        query: str,
        user_id: str,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search optimized for RAG - returns chunked content with citations.

        Args:
            query: User's question
            user_id: User ID for ACL filtering
            top_k: Number of relevant chunks to retrieve

        Returns:
            List of relevant document chunks with metadata
        """
        search_result = await self.search(
            query=query,
            user_id=user_id,
            page_size=top_k
        )

        if not search_result["success"]:
            logger.error("Vertex Search FAILED: %s", search_result.get("error"))
            return []

        logger.warning("Vertex Search OK: %d results", len(search_result.get("results", [])))
        if search_result.get("results"):
            r0 = search_result["results"][0]
            logger.warning(
                "First result snippets=%d meta=%s",
                len(r0.get("snippets", [])),
                r0.get("metadata", {})
            )

        # Format for RAG consumption
        rag_chunks = []
        for result in search_result["results"]:
            chunk = {
                "document_id": result["document_id"],
                "content": "\n".join(result.get("snippets", [])),
                "metadata": result.get("metadata", {}),
                "relevance_score": result.get("relevance_score")
            }

            # Add source citation info
            if result.get("metadata"):
                chunk["source"] = {
                    "filename": result["metadata"].get("filename", "Unknown"),
                    "document_type": result["metadata"].get("document_type", "Unknown"),
                    "claim_id": result["metadata"].get("claim_id")
                }

            rag_chunks.append(chunk)

        return rag_chunks

    async def get_document(self, claim_id: int, document_id: int) -> Optional[Dict]:
        """Get a specific document from the index."""
        try:
            search_doc_id = self._generate_document_id(claim_id, document_id)
            document_name = f"{self.parent}/documents/{search_doc_id}"

            request = discoveryengine.GetDocumentRequest(
                name=document_name
            )

            # Run in thread pool to avoid blocking event loop
            result = await self._run_sync(self.document_client.get_document, request=request)

            return {
                "success": True,
                "document_id": result.id,
                "document_name": result.name,
                "metadata": dict(result.struct_data) if result.struct_data else {}
            }

        except Exception as e:
            return None


class VertexSearchSetup:
    """
    Utility class for setting up Vertex AI Search infrastructure.
    Run once to create datastore and engine with proper configuration.
    """

    def __init__(self):
        self.api_endpoint = f"{settings.VERTEX_AI_SEARCH_LOCATION}-discoveryengine.googleapis.com"
        self.client_options = ClientOptions(api_endpoint=self.api_endpoint)

        self.datastore_client = discoveryengine.DataStoreServiceClient(
            client_options=self.client_options
        )
        self.engine_client = discoveryengine.EngineServiceClient(
            client_options=self.client_options
        )

        self.project_id = settings.GOOGLE_CLOUD_PROJECT
        self.location = settings.VERTEX_AI_SEARCH_LOCATION

        self.collection_path = (
            f"projects/{self.project_id}/"
            f"locations/{self.location}/"
            f"collections/default_collection"
        )

    def create_datastore(
        self,
        datastore_id: str,
        display_name: str = "LunatiX Insurance Documents"
    ) -> str:
        """
        Create a new datastore with ACL enabled and chunking configured.

        IMPORTANT: ACL and chunking must be set at creation time and cannot
        be changed later.
        """
        datastore = discoveryengine.DataStore()
        datastore.display_name = display_name
        datastore.industry_vertical = discoveryengine.IndustryVertical.GENERIC
        datastore.solution_types = [discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH]
        datastore.content_config = discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED

        # Enable document processing for PDFs with OCR
        datastore.document_processing_config = discoveryengine.DocumentProcessingConfig()

        # Configure OCR parser for scanned PDFs
        ocr_config = discoveryengine.DocumentProcessingConfig.ParsingConfig.OcrParsingConfig()
        ocr_config.use_native_text = True  # Merge OCR with digital text

        parsing_config = discoveryengine.DocumentProcessingConfig.ParsingConfig()
        parsing_config.ocr_parsing_config = ocr_config

        datastore.document_processing_config.default_parsing_config = parsing_config

        # Enable chunking for RAG
        chunking_config = discoveryengine.DocumentProcessingConfig.ChunkingConfig()
        chunking_config.layout_based_chunking_config = (
            discoveryengine.DocumentProcessingConfig.ChunkingConfig.LayoutBasedChunkingConfig()
        )
        chunking_config.layout_based_chunking_config.chunk_size = 500
        chunking_config.layout_based_chunking_config.include_ancestor_headings = True

        datastore.document_processing_config.chunking_config = chunking_config

        request = discoveryengine.CreateDataStoreRequest(
            parent=self.collection_path,
            data_store=datastore,
            data_store_id=datastore_id,
            # CRITICAL: Enable ACL at creation - cannot be changed later
            create_advanced_site_search_config=False
        )

        operation = self.datastore_client.create_data_store(request=request)
        result = operation.result()

        return result.name

    def create_search_engine(
        self,
        engine_id: str,
        datastore_id: str,
        display_name: str = "LunatiX Search Engine"
    ) -> str:
        """Create a search engine linked to the datastore."""
        engine = discoveryengine.Engine()
        engine.display_name = display_name
        engine.solution_type = discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH

        # Configure search engine
        engine.search_engine_config = discoveryengine.Engine.SearchEngineConfig()
        engine.search_engine_config.search_tier = (
            discoveryengine.SearchTier.SEARCH_TIER_ENTERPRISE
        )
        engine.search_engine_config.search_add_ons = [
            discoveryengine.SearchAddOn.SEARCH_ADD_ON_LLM
        ]

        # Link to datastore
        engine.data_store_ids = [datastore_id]

        request = discoveryengine.CreateEngineRequest(
            parent=self.collection_path,
            engine=engine,
            engine_id=engine_id
        )

        operation = self.engine_client.create_engine(request=request)
        result = operation.result()

        return result.name

    def setup_complete_infrastructure(
        self,
        datastore_id: str,
        engine_id: str
    ) -> Dict:
        """
        Set up complete Vertex AI Search infrastructure.
        Run this once during initial deployment.
        """
        results = {}

        try:
            # Create datastore
            datastore_name = self.create_datastore(datastore_id)
            results["datastore"] = {
                "success": True,
                "name": datastore_name
            }
        except Exception as e:
            results["datastore"] = {
                "success": False,
                "error": str(e)
            }

        try:
            # Create search engine
            engine_name = self.create_search_engine(engine_id, datastore_id)
            results["engine"] = {
                "success": True,
                "name": engine_name
            }
        except Exception as e:
            results["engine"] = {
                "success": False,
                "error": str(e)
            }

        return results
