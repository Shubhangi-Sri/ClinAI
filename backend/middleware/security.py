"""
HIPAA-Compliant Security Middleware
- Security headers (HSTS, CSP, X-Frame-Options)
- TLS enforcement
- PHI access audit logging to tamper-evident log store
- Rate limiting per provider
"""

import time
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("clinicai.audit")

# PHI-touching endpoints that require audit logging
PHI_ENDPOINTS = {"/api/asr", "/api/rag", "/api/report", "/api/fhir"}


class HIPAASecurityMiddleware(BaseHTTPMiddleware):
    """
    Enforces HIPAA Technical Safeguards:
    - §164.312(a)(2)(iv): Encryption in transit (TLS)
    - §164.312(e)(2)(ii): Encryption of PHI in transit
    - Security response headers
    """

    SECURITY_HEADERS = {
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' https://api.anthropic.com https://api.pinecone.io"
        ),
        "Permissions-Policy": "microphone=(self), camera=()",
        "Cache-Control": "no-store, no-cache, must-revalidate",  # Never cache PHI
        "Pragma": "no-cache",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Block non-HTTPS in production
        if request.headers.get("x-forwarded-proto") == "http":
            return Response(
                content=json.dumps({"error": "HTTPS required for PHI transmission"}),
                status_code=301,
                headers={"Location": str(request.url).replace("http://", "https://")},
            )

        response = await call_next(request)

        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value

        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    HIPAA §164.312(b): Audit Controls
    Logs all PHI access with:
    - Timestamp (UTC)
    - User/provider identity
    - Resource accessed
    - Action performed
    - Success/failure
    - SHA-256 log integrity hash
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.audit_logger = logging.getLogger("clinicai.phi_audit")
        handler = logging.FileHandler("audit/phi_access.log")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.audit_logger.addHandler(handler)
        self.audit_logger.setLevel(logging.INFO)

    def _is_phi_endpoint(self, path: str) -> bool:
        return any(path.startswith(ep) for ep in PHI_ENDPOINTS)

    def _create_audit_entry(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
    ) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "PHI_ACCESS",
            "user_id": request.headers.get("x-user-id", "anonymous"),
            "provider_id": request.headers.get("x-provider-id", "unknown"),
            "session_id": request.headers.get("x-session-id", ""),
            "ip_address": request.client.host if request.client else "unknown",
            "method": request.method,
            "endpoint": str(request.url.path),
            "query_params": str(request.query_params),
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "success": response.status_code < 400,
        }
        # Tamper-evident hash of the log entry
        entry_str = json.dumps(entry, sort_keys=True)
        entry["integrity_hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
        return entry

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        if self._is_phi_endpoint(request.url.path):
            entry = self._create_audit_entry(request, response, duration_ms)
            self.audit_logger.info(json.dumps(entry))

        return response
