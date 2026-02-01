"""
Authentication module - derives user_id from JWT token, not from request body.
This is critical for security: prevents users from accessing other users' documents.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings


# Security scheme
security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    user_id: str
    email: Optional[str] = None
    exp: Optional[datetime] = None


class User(BaseModel):
    user_id: str
    email: Optional[str] = None


def create_access_token(user_id: str, email: Optional[str] = None) -> str:
    """Create a JWT access token for a user."""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "email": email,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenData(
            user_id=user_id,
            email=payload.get("email"),
            exp=payload.get("exp")
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """
    Get current user from JWT token.

    SECURITY: This is the ONLY way to get user_id in API endpoints.
    Never trust user_id from request body/params.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(credentials.credentials)
    return User(user_id=token_data.user_id, email=token_data.email)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.
    Use for endpoints that work both authenticated and anonymously.
    """
    if credentials is None:
        return None

    try:
        token_data = verify_token(credentials.credentials)
        return User(user_id=token_data.user_id, email=token_data.email)
    except HTTPException:
        return None
