export enum ClaimStatus {
  SUBMITTED = 'submitted',
  DOCUMENTS_PENDING = 'documents_pending',
  UNDER_REVIEW = 'under_review',
  ADDITIONAL_INFO_REQUIRED = 'additional_info_required',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  PAID = 'paid',
}

export enum DocumentType {
  IDENTITY = 'identity',
  MEDICAL_REPORT = 'medical_report',
  INVOICE = 'invoice',
  POLICE_REPORT = 'police_report',
  PROOF_OF_OWNERSHIP = 'proof_of_ownership',
  PHOTOS = 'photos',
  OTHER = 'other',
}

export enum VerificationStatus {
  PENDING = 'pending',
  VERIFIED = 'verified',
  REJECTED = 'rejected',
  PARTIALLY_COMPLIANT = 'partially_compliant',
}

export interface Claim {
  id: number
  claim_number: string
  user_id: string
  claim_type: string
  description: string
  claim_amount: number
  status: ClaimStatus
  status_message: string | null
  created_at: string
  updated_at: string
}

export interface Document {
  id: number
  claim_id: number
  document_type: DocumentType
  filename: string
  file_path: string
  file_size: number
  mime_type: string
  verification_status: VerificationStatus
  ai_analysis: string | null
  confidence_score: number | null
  is_compliant: boolean
  compliance_issues: string | null
  uploaded_at: string
  verified_at: string | null
}

export interface ChatSource {
  label: string
  url?: string | null
}

export interface ChatMessage {
  session_id: string
  message: string
  response: string
  sources: ChatSource[]
  timestamp: string
}

export interface CreateClaimRequest {
  user_id: string
  claim_type: string
  description: string
  claim_amount: number
}
