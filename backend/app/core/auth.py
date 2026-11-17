import functools
import json
import urllib.request
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import clerk_authorized_parties, clerk_issuer, clerk_jwks_url

_bearer = HTTPBearer(auto_error=False)


# simplest: keys are cached for the process lifetime; a Clerk key rotation needs a restart.
# functools.cache never stores a raised exception, so a failed fetch is retried next request.
@functools.cache
def jwk_set(url: str) -> jwt.PyJWKSet:
    with urllib.request.urlopen(url, timeout=10) as response:
        return jwt.PyJWKSet.from_dict(json.load(response))


def current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Verify the Clerk session JWT from the bearer header and return its `sub` claim."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing session token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    token = credentials.credentials
    # outside the try: a missing setting is a 500, not a 401
    url = clerk_jwks_url()
    issuer = clerk_issuer()
    parties = clerk_authorized_parties()
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        raise unauthorized from None
    try:
        keys = jwk_set(url)
    # OSError: network error or timeout; ValueError: not JSON;
    # TypeError, AttributeError, PyJWTError: JSON that is not a JWKS.
    except (OSError, ValueError, TypeError, AttributeError, jwt.PyJWTError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch Clerk signing keys; try again later",
        ) from None
    try:
        claims = jwt.decode(
            token,
            keys[kid].key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "nbf", "sub", "iss"]},
        )
    except (jwt.PyJWTError, KeyError):
        raise unauthorized from None
    if parties and claims.get("azp") not in parties:
        raise unauthorized
    if not claims["sub"]:
        raise unauthorized
    return claims["sub"]
