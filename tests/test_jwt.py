from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt

import app.core.jwt as jwt_module
from app.core.jwt import create_access_token, decode_token


@pytest.fixture(autouse=True)
def patch_jwt_constants(monkeypatch):
    monkeypatch.setattr("app.core.jwt.KEY", "testsecret")
    monkeypatch.setattr("app.core.jwt.ALGORITHM", "HS256")
    monkeypatch.setattr("app.core.jwt.EXPIRY", 60)


def test_create_access_token_and_decode():
    """Ensure a token can be created and then decoded successfully."""

    token = create_access_token({"sub": "user123"}, token_version=1)
    assert isinstance(token, str)

    payload = decode_token(token)
    assert payload["sub"] == "user123"
    assert payload["ver"] == 1
    assert isinstance(payload["exp"], int)
    assert set(payload.keys()) >= {"sub", "exp", "ver"}

    now = datetime.now(timezone.utc).timestamp()
    assert payload["exp"] == pytest.approx(now + jwt_module.EXPIRY, abs=2)


@pytest.mark.parametrize(
    "token_factory",
    [
        # Invalid signature
        (
            lambda: jwt.encode(
                {"sub": "user123"}, "wrongkey", algorithm=jwt_module.ALGORITHM
            )
        ),
        # Expired token
        (
            lambda: jwt.encode(
                {
                    "sub": "user123",
                    "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
                },
                jwt_module.KEY,
                algorithm=jwt_module.ALGORITHM,
            )
        ),
        # Malformed token
        (lambda: "header.payload"),
    ],
)
def test_decode_token_failures(token_factory):
    """All invalid tokens should raise HTTPException with 400."""
    token = token_factory()
    with pytest.raises(HTTPException) as exc:
        decode_token(token)

    assert exc.value.status_code == 400
    assert "Token could not be validated" in exc.value.detail
