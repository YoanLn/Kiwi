from enum import Enum


class WorkflowType(str, Enum):
    """Workflow types supported by assistant services."""

    INSURANCE_CLAIM = "insurance_claim"
    FILE_MANAGEMENT = "file_management"


__all__ = ["WorkflowType"]
