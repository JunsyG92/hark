"""Authentication / authorization dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..auth import Scope, tokens_equal

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Who is calling. ``source`` is what gets recorded on proposed tasks."""

    name: str
    scopes: frozenset[Scope]
    source: str


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    master: str = request.app.state.master_token
    if tokens_equal(creds.credentials, master):
        return Principal("ui", frozenset(Scope), "manual")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


def require(scope: Scope):  # type: ignore[no-untyped-def]
    def checker(principal: Principal = Depends(get_principal)) -> Principal:  # noqa: B008
        if scope not in principal.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"scope '{scope}' required")
        return principal

    return checker


ReadScope = Annotated[Principal, Depends(require(Scope.READ))]
ProposeScope = Annotated[Principal, Depends(require(Scope.PROPOSE))]
UiScope = Annotated[Principal, Depends(require(Scope.UI))]
