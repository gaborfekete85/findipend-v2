import functools
import json
import urllib.request
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import clerk_jwks_url

_bearer = HTTPBearer(auto_error=False)


# simplest: keys are cached for the process lifetime; a Clerk key rotation needs a restart.
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
    url = clerk_jwks_url()  # outside the try: a missing setting is a 500, not a 401
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        key = jwk_set(url)[kid]
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            options={"require": ["exp", "nbf", "sub"]},
        )
    except (jwt.PyJWTError, KeyError):
        raise unauthorized from None
    return claims["sub"]
