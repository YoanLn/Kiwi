"""
Multi-step document validation workflow.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Dict, Any, TypedDict

from app.schemas.workflow import WorkflowType
from app.verification.schemas import (
    VerificationDocumentType,
    DocumentValidationStatus,
    DocumentValidationResult,
    ValidationIssue,
)
from app.verification.agents import (
    DocumentParserAgent,
    ValidatorAgent,
    CoherenceCheckerAgent,
)

logger = logging.getLogger(__name__)


class GraphState(TypedDict):
    """State for the validation workflow."""

    document_id: str
    ocr_text: str
    document_type: str
    workflow_type: str
    extracted_data: Dict[str, Any]
    validation_issues: list
    agent_outputs: Dict[str, Any]
    current_agent: str
    is_complete: bool
    needs_human_review: bool
    final_decision: str
    error: str


class DocumentValidationGraph:
    """Sequential workflow for document validation using multiple agents."""

    def __init__(self) -> None:
        self.parser_agent = DocumentParserAgent()
        self.validator_agent = ValidatorAgent()
        self.coherence_checker_agent = CoherenceCheckerAgent()
        logger.info("Document Validation Graph initialized")

    async def _run_parser(self, state: GraphState) -> GraphState:
        logger.info("Running Parser agent for document %s", state["document_id"])

        try:
            response = await self.parser_agent.analyze(
                ocr_text=state["ocr_text"],
                document_type=VerificationDocumentType(state["document_type"]),
                workflow_type=WorkflowType(state["workflow_type"]),
                extracted_data=state["extracted_data"],
                previous_findings={},
            )

            state["current_agent"] = "parser"
            state["agent_outputs"]["parser"] = response.model_dump()

            is_valid_type = response.findings.get("is_valid_document_type", True)
            if not is_valid_type:
                logger.warning(
                    "Document %s rejected as unrelated to insurance",
                    state["document_id"],
                )
                state["error"] = "Document rejected: Not a valid insurance document type"

            if response.findings.get("extracted_fields"):
                state["extracted_data"].update(response.findings["extracted_fields"])

            for issue in response.issues:
                state["validation_issues"].append(
                    issue.model_dump() if hasattr(issue, "model_dump") else issue
                )

        except Exception as exc:
            logger.error("Parser agent error: %s", exc)
            state["error"] = f"Parser error: {str(exc)}"

        return state

    async def _run_validator(self, state: GraphState) -> GraphState:
        logger.info("Running Validator agent for document %s", state["document_id"])

        try:
            response = await self.validator_agent.analyze(
                ocr_text=state["ocr_text"],
                document_type=VerificationDocumentType(state["document_type"]),
                workflow_type=WorkflowType(state["workflow_type"]),
                extracted_data=state["extracted_data"],
                previous_findings=state["agent_outputs"].get("parser", {}),
            )

            state["current_agent"] = "validator"
            state["agent_outputs"]["validator"] = response.model_dump()

            for issue in response.issues:
                state["validation_issues"].append(
                    issue.model_dump() if hasattr(issue, "model_dump") else issue
                )

        except Exception as exc:
            logger.error("Validator agent error: %s", exc)
            state["error"] = f"Validator error: {str(exc)}"

        return state

    async def _run_coherence_checker(self, state: GraphState) -> GraphState:
        logger.info("Running Coherence Checker for document %s", state["document_id"])

        try:
            response = await self.coherence_checker_agent.analyze(
                ocr_text=state["ocr_text"],
                document_type=VerificationDocumentType(state["document_type"]),
                workflow_type=WorkflowType(state["workflow_type"]),
                extracted_data=state["extracted_data"],
                previous_findings={
                    "parser": state["agent_outputs"].get("parser", {}),
                    "validator": state["agent_outputs"].get("validator", {}),
                },
            )

            state["current_agent"] = "coherence_checker"
            state["agent_outputs"]["coherence_checker"] = response.model_dump()

            for issue in response.issues:
                state["validation_issues"].append(
                    issue.model_dump() if hasattr(issue, "model_dump") else issue
                )

            if response.findings.get("requires_human_review", False):
                state["needs_human_review"] = True

        except Exception as exc:
            logger.error("Coherence Checker error: %s", exc)
            state["error"] = f"Coherence Checker error: {str(exc)}"

        return state

    async def _make_decision(self, state: GraphState) -> GraphState:
        logger.info("Making final decision for document %s", state["document_id"])

        state["current_agent"] = "decision_maker"
        state["is_complete"] = True

        parser_output = state["agent_outputs"].get("parser", {})
        parser_findings = parser_output.get("findings", {})
        is_valid_type = parser_findings.get("is_valid_document_type", True)

        if not is_valid_type:
            state["final_decision"] = (
                "REJECTED - Document is not a valid insurance document type"
            )
            state["needs_human_review"] = False
            return state

        critical_issues = [
            i for i in state["validation_issues"] if i.get("severity") == "critical"
        ]
        high_issues = [
            i for i in state["validation_issues"] if i.get("severity") == "high"
        ]
        medium_issues = [
            i for i in state["validation_issues"] if i.get("severity") == "medium"
        ]

        validator_output = state["agent_outputs"].get("validator", {})
        validator_findings = validator_output.get("findings", {})
        is_complete = validator_findings.get("is_complete", True)
        completeness_score = validator_findings.get("completeness_score", 1.0)

        coherence_output = state["agent_outputs"].get("coherence_checker", {})
        coherence_findings = coherence_output.get("findings", {})
        is_coherent = coherence_findings.get("is_coherent", True)
        coherence_score = coherence_findings.get("coherence_score", 1.0)

        if critical_issues:
            state["final_decision"] = "INVALID - Critical issues detected"
            state["needs_human_review"] = True
        elif high_issues:
            state["final_decision"] = "NEEDS_REVIEW - Significant issues found"
            state["needs_human_review"] = True
        elif not is_complete or completeness_score < 0.7:
            state["final_decision"] = "INCOMPLETE - Missing required information"
            state["needs_human_review"] = True
        elif not is_coherent or coherence_score < 0.7:
            state["final_decision"] = "NEEDS_REVIEW - Data inconsistencies detected"
            state["needs_human_review"] = True
        elif medium_issues:
            state["final_decision"] = "VALID_WITH_NOTES - Valid with minor issues"
        else:
            state["final_decision"] = "VALID - Document passed all checks"

        return state

    async def validate_document(
        self,
        document_id: str,
        ocr_text: str,
        document_type: VerificationDocumentType,
        workflow_type: WorkflowType,
    ) -> DocumentValidationResult:
        """Run the full validation workflow on a document."""
        start_time = time.time()

        initial_state: GraphState = {
            "document_id": document_id,
            "ocr_text": ocr_text,
            "document_type": document_type.value,
            "workflow_type": workflow_type.value,
            "extracted_data": {},
            "validation_issues": [],
            "agent_outputs": {},
            "current_agent": "",
            "is_complete": False,
            "needs_human_review": False,
            "final_decision": "",
            "error": "",
        }

        try:
            state = await self._run_parser(initial_state)
            state = await self._run_validator(state)
            state = await self._run_coherence_checker(state)
            state = await self._make_decision(state)
        except Exception as exc:
            logger.error("Validation pipeline error: %s", exc)
            state = initial_state
            state["error"] = str(exc)
            state["final_decision"] = "ERROR - Validation process failed"
            state["is_complete"] = True

        processing_time = time.time() - start_time

        decision = state.get("final_decision", "")
        if "REJECTED" in decision:
            overall_status = DocumentValidationStatus.INVALID
        elif "VALID" in decision and "INVALID" not in decision:
            overall_status = DocumentValidationStatus.VALID
        elif "INVALID" in decision:
            overall_status = DocumentValidationStatus.INVALID
        elif "NEEDS_REVIEW" in decision or state.get("needs_human_review"):
            overall_status = DocumentValidationStatus.NEEDS_REVIEW
        else:
            overall_status = DocumentValidationStatus.INVALID

        issues = []
        for issue_dict in state.get("validation_issues", []):
            if isinstance(issue_dict, dict):
                issues.append(
                    ValidationIssue(
                        field=issue_dict.get("field", "unknown"),
                        issue_type=issue_dict.get("issue_type", "unknown"),
                        description=issue_dict.get("description", ""),
                        severity=issue_dict.get("severity", "medium"),
                        suggestion=issue_dict.get("suggestion"),
                        confidence=issue_dict.get("confidence", 0.8),
                    )
                )

        return DocumentValidationResult(
            document_id=document_id,
            is_valid=overall_status == DocumentValidationStatus.VALID,
            overall_status=overall_status,
            issues=issues,
            extracted_data=state.get("extracted_data", {}),
            agent_reports=state.get("agent_outputs", {}),
            processing_time=processing_time,
            summary=state.get("final_decision", "Validation completed"),
        )


@lru_cache()
def get_validation_graph() -> DocumentValidationGraph:
    """Get cached validation graph instance."""
    return DocumentValidationGraph()
