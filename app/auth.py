"""FastAPI bearer-token authentication dependency."""

import hashlib
import math
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.dependencies import get_services
from app.models import UserRecord
from app.services import ApplicationServices


_bearer_scheme = HTTPBearer(auto_error=False)
_MAX_TOKEN_LENGTH = 512


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    services: Annotated[ApplicationServices, Depends(get_services)],
) -> UserRecord:
    """Resolve a bearer token to an active user without logging credentials."""
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
        or len(credentials.credentials) > _MAX_TOKEN_LENGTH
    ):
        raise _unauthorized()

    token_hash = hashlib.sha256(
        credentials.credentials.encode("utf-8")
    ).hexdigest()
    user = services.store.get_active_user_for_token_hash(token_hash)
    if user is None:
        raise _unauthorized()
    return user


def get_rate_limited_user(
    request: Request,
    current_user: Annotated[UserRecord, Depends(get_authenticated_user)],
) -> UserRecord:
    """Authenticate, then enforce the configured per-user request window."""
    retry_after = request.app.state.rate_limiter.consume(current_user.user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request limit exceeded. Try again later.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
    return current_user
