from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel

from app.schemas.workflow import WorkflowType


class VerificationDocumentType(str, Enum):
    """Document types supported by the verification agents."""

    INSURANCE_POLICY = "insurance_policy"
    CLAIM_FORM = "claim_form"
    INCIDENT_REPORT = "incident_report"
    PROOF_OF_OWNERSHIP = "proof_of_ownership"
    EVIDENCE_OF_DAMAGE = "evidence_of_damage"
    REPAIR_ESTIMATE = "repair_estimate"
    MEDICAL_REPORT = "medical_report"
    ID_DOCUMENT = "id_document"
    BANK_DETAILS = "bank_details"
    UNRELATED = "unrelated"


class DocumentValidationStatus(str, Enum):
    """Status of document validation."""

    PENDING = "pending"
    PROCESSING = "processing"
    VALID = "valid"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


class ValidationIssue(BaseModel):
    """A single validation issue."""

    field: str
    issue_type: str  # missing, invalid, inconsistent, suspicious, unrelated_document
    description: str
    severity: str  # low, medium, high, critical
    suggestion: Optional[str] = None
    confidence: float = 0.8


class DocumentValidationResult(BaseModel):
    """Result of document validation by multi-agent system."""

    document_id: str
    is_valid: bool
    overall_status: DocumentValidationStatus
    issues: List[ValidationIssue] = []
    extracted_data: Optional[Dict[str, Any]] = None
    agent_reports: Dict[str, Dict[str, Any]] = {}
    processing_time: float
    summary: str


class AgentResponse(BaseModel):
    """Response from an individual agent."""

    agent_name: str
    status: str
    findings: Dict[str, Any]
    issues: List[ValidationIssue] = []
    confidence: float
    reasoning: str


__all__ = [
    "WorkflowType",
    "VerificationDocumentType",
    "DocumentValidationStatus",
    "ValidationIssue",
    "DocumentValidationResult",
    "AgentResponse",
]
