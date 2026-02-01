"""
Authentication routes for token generation and user management.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.core.auth import create_access_token, get_current_user, User

router = APIRouter()


class LoginRequest(BaseModel):
    user_id: str
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


@router.post("/token", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Generate an access token for a user.

    NOTE: In production, this should validate credentials against a real auth system
    (e.g., Google OAuth, Auth0, Firebase Auth). For hackathon purposes, this generates
    a token for any user_id provided.

    TODO for production:
    - Integrate with OIDC provider
    - Validate user credentials
    - Store user info in database
    """
    access_token = create_access_token(
        user_id=request.user_id,
        email=request.email
    )

    return TokenResponse(
        access_token=access_token,
        user_id=request.user_id
    )


@router.get("/me", response_model=User)
async def get_me(current_user: User = None):
    """Get current authenticated user info."""
    from fastapi import Depends
    # This endpoint requires the dependency to be added at route level
    # For now, it's a placeholder
    return current_user
