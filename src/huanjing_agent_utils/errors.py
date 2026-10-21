"""Validation base classes retained for the standalone component."""


class GovernanceError(Exception):
    """Governance 基类异常。"""


class GovernanceValidationError(GovernanceError):
    """契约字段/状态非法。"""
