"""
Agents for the multi-step document verification workflow.
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

import vertexai
from vertexai.generative_models import GenerativeModel

from app.core.config import settings
from app.schemas.workflow import WorkflowType
from app.verification.schemas import (
    AgentResponse,
    ValidationIssue,
    VerificationDocumentType,
)

logger = logging.getLogger(__name__)


def _ensure_vertex_ai():
    """Initialize Vertex AI once for all agents."""
    vertexai.init(
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.VERTEX_AI_LOCATION,
    )


class BaseAgent(ABC):
    """Base class for all validation agents."""

    def __init__(self, name: str):
        self.name = name
        _ensure_vertex_ai()
        self.model = GenerativeModel(settings.VERTEX_AI_MODEL_TEXT)

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt for this agent."""

    @abstractmethod
    def get_analysis_prompt(
        self,
        ocr_text: str,
        document_type: VerificationDocumentType,
        workflow_type: WorkflowType,
        extracted_data: Dict[str, Any],
        previous_findings: Dict[str, Any],
    ) -> str:
        """Get the analysis prompt for this agent."""

    async def analyze(
        self,
        ocr_text: str,
        document_type: VerificationDocumentType,
        workflow_type: WorkflowType,
        extracted_data: Dict[str, Any],
        previous_findings: Dict[str, Any],
    ) -> AgentResponse:
        """Run analysis on the document."""
        try:
            system_prompt = self.get_system_prompt()
            analysis_prompt = self.get_analysis_prompt(
                ocr_text, document_type, workflow_type, extracted_data, previous_findings
            )

            response = await asyncio.to_thread(
                self.model.generate_content,
                [system_prompt, analysis_prompt],
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2048,
                    "top_p": 0.8,
                },
            )

            response_text = getattr(response, "text", None) or str(response)

            # Parse the response
            parsed = self._parse_response(response_text)

            return AgentResponse(
                agent_name=self.name,
                status=parsed.get("status", "completed"),
                findings=parsed.get("findings", {}),
                issues=parsed.get("issues", []),
                confidence=parsed.get("confidence", 0.8),
                reasoning=parsed.get("reasoning", response_text),
            )

        except Exception as exc:
            logger.error("Agent %s analysis error: %s", self.name, exc)
            return AgentResponse(
                agent_name=self.name,
                status="error",
                findings={"error": str(exc)},
                issues=[],
                confidence=0.0,
                reasoning=f"Analysis failed: {str(exc)}",
            )

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the agent's response into structured format."""
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start != -1 and end > start:
                parsed = json.loads(response_text[start:end])

                # Convert issues to ValidationIssue objects if needed
                if "issues" in parsed:
                    issues = []
                    for issue in parsed["issues"]:
                        if isinstance(issue, dict):
                            issues.append(
                                ValidationIssue(
                                    field=issue.get("field", "unknown"),
                                    issue_type=issue.get("issue_type", "unknown"),
                                    description=issue.get("description", ""),
                                    severity=issue.get("severity", "medium"),
                                    suggestion=issue.get("suggestion"),
                                    confidence=issue.get("confidence", 0.8),
                                )
                            )
                    parsed["issues"] = issues

                return parsed
        except json.JSONDecodeError:
            pass

        return {"reasoning": response_text}


class DocumentParserAgent(BaseAgent):
    """Agent responsible for parsing and extracting structured data from documents."""

    def __init__(self):
        super().__init__("DocumentParser")

    def get_system_prompt(self) -> str:
        return """You are an expert document parser specialized in insurance-related documents.
Your task is to determine if the document is valid and extract structured information from it.

VALID DOCUMENT TYPES:
- insurance_policy: Policy documents with coverage details
- claim_form: Insurance claim forms
- incident_report: Police reports, accident reports, loss statements
- proof_of_ownership: Receipts, invoices, purchase contracts
- evidence_of_damage: Photos or descriptions of damage
- repair_estimate: Repair quotes or invoices
- medical_report: Medical records, bills, diagnoses
- id_document: ID cards, passports, driver licenses
- bank_details: Bank statements, RIB, account information

If the document does NOT match any valid type, mark it as "unrelated".

Respond in JSON format:
{
    "status": "completed" or "rejected",
    "confidence": 0.0 to 1.0,
    "findings": {
        "document_type_detected": "type or 'unrelated'",
        "is_valid_document_type": true or false,
        "extracted_fields": {
            "holder_name": "full name if found",
            "date_of_birth": "if found",
            "address": "if found",
            "id_number": "ID/passport number if found",
            "bank_account": "IBAN or account number if found",
            "bank_name": "if found",
            "policy_number": "if found",
            "claim_number": "if found",
            "amounts": [],
            "dates": []
        }
    },
    "issues": [
        {
            "field": "field_name",
            "issue_type": "missing" or "unclear" or "unrelated_document",
            "description": "description",
            "severity": "low" or "medium" or "high" or "critical",
            "confidence": 0.0 to 1.0
        }
    ],
    "reasoning": "brief explanation"
}"""

    def get_analysis_prompt(
        self,
        ocr_text: str,
        document_type: VerificationDocumentType,
        workflow_type: WorkflowType,
        extracted_data: Dict[str, Any],
        previous_findings: Dict[str, Any],
    ) -> str:
        return f"""Parse this document and extract all relevant information.

Document Type Hint: {document_type.value}

OCR Text:
---
{ocr_text[:8000]}
---

Tasks:
1. Verify this is a valid insurance-related document
2. Extract key fields: names, dates, ID numbers, addresses, bank details, amounts
3. Report any missing or unclear information

Focus on extracting identity and financial information that can be cross-verified with other documents.

Respond in JSON format."""


class ValidatorAgent(BaseAgent):
    """Agent responsible for validating document completeness and data quality."""

    def __init__(self):
        super().__init__("Validator")

    def get_system_prompt(self) -> str:
        return """You are a document validator that checks completeness and data quality.

For each document type, verify required fields are present and readable:
- id_document: name, ID number, date of birth, expiry date
- bank_details: account holder name, IBAN/account number, bank name
- claim_form: claimant name, claim description, date
- insurance_policy: policy number, holder name, coverage dates
- incident_report: date, description, location
- proof_of_ownership: item, purchase date, owner name
- repair_estimate: item, cost, provider
- medical_report: patient name, date, diagnosis

Respond in JSON format:
{
    "status": "completed" or "needs_review" or "rejected",
    "confidence": 0.0 to 1.0,
    "findings": {
        "is_complete": true or false,
        "completeness_score": 0.0 to 1.0,
        "fields_found": [],
        "fields_missing": [],
        "data_quality_score": 0.0 to 1.0
    },
    "issues": [
        {
            "field": "field_name",
            "issue_type": "missing" or "invalid" or "illegible",
            "description": "description",
            "severity": "low" or "medium" or "high",
            "confidence": 0.0 to 1.0
        }
    ],
    "reasoning": "brief explanation"
}"""

    def get_analysis_prompt(
        self,
        ocr_text: str,
        document_type: VerificationDocumentType,
        workflow_type: WorkflowType,
        extracted_data: Dict[str, Any],
        previous_findings: Dict[str, Any],
    ) -> str:
        parser_findings = previous_findings.get("findings", {})
        if not parser_findings.get("is_valid_document_type", True):
            return f"""Document was marked as unrelated. Confirm rejection.

Parser Findings: {json.dumps(previous_findings, indent=2)}

Set status to "rejected" and is_complete to false. Respond in JSON format."""

        return f"""Validate this {document_type.value} document for completeness.

OCR Text:
---
{ocr_text[:6000]}
---

Extracted Data:
{json.dumps(extracted_data, indent=2)}

Check:
1. Required fields for {document_type.value} are present
2. Data is readable and properly formatted
3. No critical information is missing

Respond in JSON format."""


class CoherenceCheckerAgent(BaseAgent):
    """Agent that verifies consistency and coherence across documents."""

    def __init__(self):
        super().__init__("CoherenceChecker")

    def get_system_prompt(self) -> str:
        return """You are a document coherence checker that verifies information consistency.

Your role is to check if extracted data is internally consistent and would be coherent
with other documents from the same person (e.g., ID card and bank details should have the same name).

Key checks:
1. Name consistency: Does the name match expected format? Is it complete?
2. Date consistency: Are dates logical (not in future, birth date reasonable)?
3. ID numbers: Are they in valid format for the document type?
4. Bank details: Is IBAN format valid? Does holder name match?
5. Addresses: Are they complete and properly formatted?
6. Cross-reference potential: Can this document be verified against others?

Respond in JSON format:
{
    "status": "completed" or "needs_review",
    "confidence": 0.0 to 1.0,
    "findings": {
        "is_coherent": true or false,
        "coherence_score": 0.0 to 1.0,
        "verified_fields": ["field1", "field2"],
        "inconsistencies": [],
        "cross_reference_fields": {
            "name": "extracted name for cross-reference",
            "date_of_birth": "if found",
            "id_number": "if found",
            "address": "if found"
        },
        "requires_human_review": true or false
    },
    "issues": [
        {
            "field": "field_name",
            "issue_type": "inconsistency" or "format_error" or "suspicious",
            "description": "description",
            "severity": "low" or "medium" or "high",
            "confidence": 0.0 to 1.0
        }
    ],
    "reasoning": "brief explanation"
}"""

    def get_analysis_prompt(
        self,
        ocr_text: str,
        document_type: VerificationDocumentType,
        workflow_type: WorkflowType,
        extracted_data: Dict[str, Any],
        previous_findings: Dict[str, Any],
    ) -> str:
        parser_findings = previous_findings.get("parser", {}).get("findings", {})
        if not parser_findings.get("is_valid_document_type", True):
            return f"""Document was rejected as unrelated. Confirm rejection.

Previous Findings: {json.dumps(previous_findings, indent=2)}

Set status to "rejected". Respond in JSON format."""

        return f"""Check the coherence and consistency of this {document_type.value} document.

OCR Text:
---
{ocr_text[:6000]}
---

Extracted Data:
{json.dumps(extracted_data, indent=2)}

Previous Findings:
{json.dumps(previous_findings, indent=2)}

Verify:
1. Names are properly formatted (first name, last name)
2. Dates are logical and in valid format
3. ID numbers match expected format for the country/document type
4. Bank details (if present) have valid IBAN format
5. All data is internally consistent within the document
6. Extract key fields that can be used to cross-verify with other documents

Note: This document may be part of a set (e.g., ID + bank details + claim form).
Extract identity information clearly so it can be compared across documents.

Respond in JSON format."""
