#!/usr/bin/env python3
"""
Setup script for Vertex AI Search infrastructure.
Run this ONCE before deploying the application.

This creates:
1. A datastore with ACL enabled (for document-level access control)
2. OCR + chunking configuration for PDF processing
3. A search engine linked to the datastore

IMPORTANT: ACL and chunking settings cannot be changed after creation!
"""

import os
import sys
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions


def setup_vertex_search(
    project_id: str,
    location: str = "eu",
    datastore_id: str = "lunatix-insurance-docs",
    engine_id: str = "lunatix-search-engine"
):
    """
    Set up Vertex AI Search infrastructure for LunatiX.

    Args:
        project_id: Google Cloud project ID
        location: Location for the datastore (use 'eu' for EU multi-region)
        datastore_id: ID for the datastore
        engine_id: ID for the search engine
    """
    print(f"Setting up Vertex AI Search infrastructure...")
    print(f"  Project: {project_id}")
    print(f"  Location: {location}")
    print(f"  Datastore: {datastore_id}")
    print(f"  Engine: {engine_id}")
    print()

    # Configure API endpoint for EU
    api_endpoint = f"{location}-discoveryengine.googleapis.com"
    client_options = ClientOptions(api_endpoint=api_endpoint)

    # Collection path
    collection_path = f"projects/{project_id}/locations/{location}/collections/default_collection"

    # Step 1: Create Datastore
    print("Step 1: Creating datastore with ACL and chunking enabled...")
    try:
        datastore_client = discoveryengine.DataStoreServiceClient(
            client_options=client_options
        )

        datastore = discoveryengine.DataStore()
        datastore.display_name = "LunatiX Insurance Documents"
        datastore.industry_vertical = discoveryengine.IndustryVertical.GENERIC
        datastore.solution_types = [discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH]
        datastore.content_config = discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED

        # Configure document processing for PDFs
        datastore.document_processing_config = discoveryengine.DocumentProcessingConfig()

        # OCR parser for scanned PDFs with native text fallback
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
            parent=collection_path,
            data_store=datastore,
            data_store_id=datastore_id
        )

        operation = datastore_client.create_data_store(request=request)
        print("  Waiting for datastore creation (this may take a few minutes)...")
        result = operation.result(timeout=600)
        print(f"  Datastore created: {result.name}")

    except Exception as e:
        if "ALREADY_EXISTS" in str(e):
            print(f"  Datastore already exists: {datastore_id}")
        else:
            print(f"  Error creating datastore: {e}")
            return False

    # Step 2: Create Search Engine
    print("\nStep 2: Creating search engine...")
    try:
        engine_client = discoveryengine.EngineServiceClient(
            client_options=client_options
        )

        engine = discoveryengine.Engine()
        engine.display_name = "LunatiX Search Engine"
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
            parent=collection_path,
            engine=engine,
            engine_id=engine_id
        )

        operation = engine_client.create_engine(request=request)
        print("  Waiting for engine creation (this may take a few minutes)...")
        result = operation.result(timeout=600)
        print(f"  Engine created: {result.name}")

    except Exception as e:
        if "ALREADY_EXISTS" in str(e):
            print(f"  Engine already exists: {engine_id}")
        else:
            print(f"  Error creating engine: {e}")
            return False

    print("\n" + "="*60)
    print("Setup complete!")
    print("="*60)
    print()
    print("IMPORTANT: Add these values to your .env file or Cloud Run config:")
    print()
    print(f"  VERTEX_AI_SEARCH_LOCATION={location}")
    print(f"  VERTEX_AI_SEARCH_DATASTORE_ID={datastore_id}")
    print(f"  VERTEX_AI_SEARCH_ENGINE_ID={engine_id}")
    print()
    print("NOTE: ACL (access control) must be configured in the Google Cloud Console:")
    print("  1. Go to Vertex AI Search > Data stores > lunatix-insurance-docs")
    print("  2. Under Settings, enable 'Data source access control'")
    print("  3. Configure your identity provider")
    print()
    print("For document-level ACL to work, documents must include acl_info when indexed.")
    print("The application handles this automatically when uploading documents.")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Set up Vertex AI Search infrastructure for LunatiX"
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="Google Cloud project ID"
    )
    parser.add_argument(
        "--location",
        default="eu",
        help="Location for Vertex AI Search (default: eu for EU multi-region)"
    )
    parser.add_argument(
        "--datastore-id",
        default="lunatix-insurance-docs",
        help="ID for the datastore"
    )
    parser.add_argument(
        "--engine-id",
        default="lunatix-search-engine",
        help="ID for the search engine"
    )

    args = parser.parse_args()

    success = setup_vertex_search(
        project_id=args.project_id,
        location=args.location,
        datastore_id=args.datastore_id,
        engine_id=args.engine_id
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
