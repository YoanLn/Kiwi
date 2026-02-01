"""
Pydantic schemas for document validation and OCR.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class WorkflowType(str, Enum):
    """Type of workflow selected by the client."""
    INSURANCE_CLAIM = "insurance_claim"
    FILE_MANAGEMENT = "file_management"


class ValidationIssue(BaseModel):
    """A single validation issue found in a document."""
    field: str
    issue_type: str  # missing, invalid, inconsistent, suspicious, unrelated_document
    description: str
    severity: str  # low, medium, high, critical
    suggestion: Optional[str] = None
    confidence: float = 0.8


class OCRResult(BaseModel):
    """Result from OCR processing."""
    document_id: str
    raw_text: str
    structured_data: Optional[Dict[str, Any]] = None
    tables: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None
    processing_time: float


class AgentResponse(BaseModel):
    """Response from an individual validation agent."""
    agent_name: str
    status: str
    findings: Dict[str, Any]
    issues: List[ValidationIssue] = []
    confidence: float
    reasoning: str


class DocumentValidationResult(BaseModel):
    """Result of document validation by multi-agent system."""
    document_id: str
    is_valid: bool
    overall_status: str  # valid, invalid, needs_review
    issues: List[ValidationIssue] = []
    extracted_data: Optional[Dict[str, Any]] = None
    agent_reports: Dict[str, Dict[str, Any]] = {}
    processing_time: float
    summary: str
