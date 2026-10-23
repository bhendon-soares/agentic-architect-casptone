"""Local authentication and authorization dependencies."""

import os
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.persistence.database import get_session
from app.persistence.models import RevokedSession, User

SESSION_SECONDS = 28800
hasher = PasswordHasher()


def secret() -> str:
    value = os.getenv("JWT_SECRET", "")
    if len(value.encode()) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 bytes")
    return value


def normalized_email(email: str) -> str:
    return email.strip().lower()


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise HTTPException(422, "PASSWORD_TOO_SHORT")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def session_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user.user_id,
            "role": user.role,
            "iat": now.timestamp(),
            "exp": now + timedelta(seconds=SESSION_SECONDS),
            "jti": str(uuid4()),
        },
        secret(),
        algorithm="HS256",
    )


def set_session_cookie(response, user: User) -> None:
    response.set_cookie(
        "session",
        session_token(user),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "true").lower() != "false",
        samesite="strict",
        path="/",
    )


def client_ip(request: Request) -> str:
    socket_ip = request.client.host if request.client else ""
    trusted = {item.strip() for item in os.getenv("TRUSTED_PROXY_IPS", "").split(",")}
    if socket_ip in trusted:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        try:
            return str(ip_address(forwarded))
        except ValueError:
            pass
    return socket_ip


def user_data(user: User) -> dict:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }


def current_user(request: Request, db: Session = Depends(get_session)) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(401, "AUTH_REQUIRED")
    try:
        claims = jwt.decode(
            token,
            secret(),
            algorithms=["HS256"],
            options={"require": ["sub", "role", "iat", "exp", "jti"]},
        )
        user = db.get(User, claims["sub"])
        if (
            user is None
            or not user.is_active
            or user.role != claims["role"]
            or db.get(RevokedSession, claims["jti"]) is not None
            or float(claims["iat"])
            < user.password_changed_at.replace(
                tzinfo=user.password_changed_at.tzinfo or timezone.utc
            ).timestamp()
        ):
            raise HTTPException(401, "INVALID_TOKEN")
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(401, "INVALID_TOKEN") from exc
    request.state.session_claims = claims
    if user.must_change_password and request.url.path not in {
        "/api/auth/me",
        "/api/auth/logout",
        "/api/auth/change-password",
    }:
        raise HTTPException(403, "PASSWORD_CHANGE_REQUIRED")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "FORBIDDEN_ROLE")
    return user
