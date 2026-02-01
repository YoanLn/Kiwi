from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class DocumentType(str, enum.Enum):
    # Valid document types for insurance claims
    INSURANCE_POLICY = "insurance_policy"
    CLAIM_FORM = "claim_form"
    INCIDENT_REPORT = "incident_report"  # Police reports, accident reports
    PROOF_OF_OWNERSHIP = "proof_of_ownership"
    EVIDENCE_OF_DAMAGE = "evidence_of_damage"
    REPAIR_ESTIMATE = "repair_estimate"
    MEDICAL_REPORT = "medical_report"
    ID_DOCUMENT = "id_document"  # ID cards, passports
    BANK_DETAILS = "bank_details"
    # Legacy types for backwards compatibility
    IDENTITY = "identity"
    INVOICE = "invoice"
    POLICE_REPORT = "police_report"
    PHOTOS = "photos"
    OTHER = "other"
    # Invalid/unrelated documents
    UNRELATED = "unrelated"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    PARTIALLY_COMPLIANT = "partially_compliant"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))

    # Document details
    document_type = Column(Enum(DocumentType))
    filename = Column(String)
    file_path = Column(String)  # GCS path
    file_size = Column(Integer)
    mime_type = Column(String)

    # AI Verification
    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    ai_analysis = Column(Text, nullable=True)
    confidence_score = Column(Integer, nullable=True)  # 0-100
    is_compliant = Column(Boolean, default=False)
    compliance_issues = Column(Text, nullable=True)

    # Timestamps
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)

    # Relationships
    claim = relationship("Claim", back_populates="documents")
