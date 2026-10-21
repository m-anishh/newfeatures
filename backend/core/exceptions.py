"""
VisionX Exception Hierarchy
Centralized, typed exception handling with structured error responses.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from fastapi import HTTPException, status


class VisionXError(Exception):
    """Base exception for all VisionX errors."""

    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "status_code": self.status_code,
                "details": self.details,
            }
        }

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_dict(),
        )


# ---- Authentication & Authorization ----

class AuthenticationError(VisionXError):
    """Invalid or missing authentication credentials."""

    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="authentication_error",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class AuthorizationError(VisionXError):
    """Insufficient permissions for the requested operation."""

    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="authorization_error",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class TokenExpiredError(AuthenticationError):
    """JWT token has expired."""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message=message)
        self.code = "token_expired"


class InvalidTokenError(AuthenticationError):
    """JWT token is invalid or malformed."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message=message)
        self.code = "invalid_token"


# ---- Resource Errors ----

class NotFoundError(VisionXError):
    """Requested resource was not found."""

    def __init__(
        self,
        resource: str = "Resource",
        resource_id: Optional[str] = None,
        message: Optional[str] = None,
    ):
        msg = message or f"{resource} not found"
        if resource_id:
            msg += f": {resource_id}"
        super().__init__(
            message=msg,
            code="not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "resource_id": resource_id},
        )


class ConflictError(VisionXError):
    """Resource conflict (e.g., duplicate entry)."""

    def __init__(self, message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="conflict",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


# ---- Validation Errors ----

class ValidationError(VisionXError):
    """Input validation failure."""

    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(
            message=message,
            code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"field_errors": field_errors or []},
        )


class FileValidationError(ValidationError):
    """File-specific validation failure."""

    def __init__(self, message: str = "Invalid file"):
        super().__init__(message=message)
        self.code = "file_validation_error"


# ---- Analysis Errors ----

class AnalysisError(VisionXError):
    """Base error for analysis pipeline failures."""

    def __init__(self, message: str = "Analysis failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="analysis_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class AgentError(VisionXError):
    """An AI agent encountered an error during execution."""

    def __init__(
        self,
        agent_name: str,
        message: str = "Agent execution failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=f"[{agent_name}] {message}",
            code="agent_error",
            status_code=500,
            details={"agent_name": agent_name, **(details or {})},
        )


class PipelineError(VisionXError):
    """Pipeline execution error."""

    def __init__(self, message: str = "Pipeline execution failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="pipeline_error",
            status_code=500,
            details=details,
        )


class OrchestratorError(VisionXError):
    """Orchestrator-level error."""

    def __init__(self, message: str = "Orchestration failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="orchestrator_error",
            status_code=500,
            details=details,
        )


# ---- Integration Errors ----

class ExternalServiceError(VisionXError):
    """Error communicating with an external service."""

    def __init__(
        self,
        service: str,
        message: str = "External service error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=f"[{service}] {message}",
            code="external_service_error",
            status_code=502,
            details={"service": service, **(details or {})},
        )


class DatabaseError(VisionXError):
    """Database operation failure."""

    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="database_error",
            status_code=500,
            details=details,
        )


class StorageError(VisionXError):
    """Storage operation failure (S3, local)."""

    def __init__(self, message: str = "Storage operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="storage_error",
            status_code=500,
            details=details,
        )


class RateLimitError(VisionXError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded. Try again later."):
        super().__init__(
            message=message,
            code="rate_limit_exceeded",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class ConfigurationError(VisionXError):
    """System configuration error."""

    def __init__(self, message: str = "Configuration error"):
        super().__init__(
            message=message,
            code="configuration_error",
            status_code=500,
        )


# ---- Graceful Degradation ----

class DegradedOperationError(VisionXError):
    """
    Raised when a non-critical component fails but the system can continue.
    The error is logged but the pipeline can proceed with reduced confidence.
    """

    def __init__(
        self,
        component: str,
        message: str = "Non-critical component failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=f"[{component}] {message}",
            code="degraded_operation",
            status_code=200,  # Non-critical; pipeline continues
            details={"component": component, **(details or {})},
        )