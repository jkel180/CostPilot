"""Verification of Supabase Auth access tokens (JWT)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt

from app.config import Settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TokenUser:
    id: uuid.UUID
    email: str


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600)


def verify_access_token(token: str, settings: Settings) -> TokenUser:
    """Validate signature, expiry, audience and issuer; return the authenticated user.

    * Legacy projects: HS256 with ``SUPABASE_JWT_SECRET``.
    * Current projects: asymmetric keys (ES256/RS256) published at ``/auth/v1/.well-known/jwks.json``.
    """
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        options = {"require": ["exp", "sub", "aud"]}
        common = {"audience": settings.jwt_audience, "options": options}
        if settings.jwt_issuer:
            common["issuer"] = settings.jwt_issuer

        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthError("HS256 tokens are not accepted: SUPABASE_JWT_SECRET is not configured")
            claims = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **common)
        elif alg in ("ES256", "RS256"):
            if not settings.supabase_url:
                raise AuthError("SUPABASE_URL is not configured")
            key = _jwks_client(f"{settings.jwt_issuer}/.well-known/jwks.json").get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=[alg], **common)
        else:
            raise AuthError(f"Unsupported token algorithm: {alg}")
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc

    email = claims.get("email")
    if not email:
        raise AuthError("Token has no email claim")
    try:
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, TypeError) as exc:
        raise AuthError("Token subject is not a valid user id") from exc
    return TokenUser(id=user_id, email=email.lower())
