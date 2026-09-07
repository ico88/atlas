"""Multi-factor auth (TOTP) — ROADMAP R5."""

from __future__ import annotations

import pytest
from app.core import totp
from app.services import user_service


# --------------------------------------------------------------------------- #
# Pure TOTP (RFC 6238)
# --------------------------------------------------------------------------- #
def test_totp_generate_verify_roundtrip():
    secret = totp.generate_secret()
    code = totp.totp_now(secret)
    assert totp.verify(secret, code) is True
    assert totp.verify(secret, "000000", at=0) is False


def test_totp_window_tolerates_skew():
    secret = totp.generate_secret()
    # A code from the previous 30s period still verifies within the window.
    prev = totp.totp_now(secret, at=1000)
    assert totp.verify(secret, prev, at=1035, window=1) is True
    assert totp.verify(secret, prev, at=1000 + 300, window=1) is False


def test_totp_rejects_garbage():
    secret = totp.generate_secret()
    assert totp.verify(secret, "abc") is False
    assert totp.verify(secret, "") is False


def test_provisioning_uri():
    uri = totp.provisioning_uri("ABC234", "user@example.com", "ATLAS")
    assert uri.startswith("otpauth://totp/ATLAS:user%40example.com?secret=ABC234")


# --------------------------------------------------------------------------- #
# Endpoints + login enforcement
# --------------------------------------------------------------------------- #
async def _make_user(session, email="mfa@example.com", pw="secret-pass") -> None:
    await user_service.create_user(session, email=email, password=pw, role="admin")


async def _login(client, email, pw, code=None):
    body = {"email": email, "password": pw}
    if code is not None:
        body["code"] = code
    return await client.post("/api/v1/auth/login", json=body)


async def _token(client, email, pw) -> str:
    r = await _login(client, email, pw)
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_mfa_setup_enable_and_login_flow(client, session):
    await _make_user(session)
    token = await _token(client, "mfa@example.com", "secret-pass")
    hdr = {"Authorization": f"Bearer {token}"}

    # Setup -> get a secret.
    r = await client.post("/api/v1/auth/mfa/setup", headers=hdr)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://")

    # Enabling with a wrong code fails; a real code succeeds.
    bad = await client.post("/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=hdr)
    assert bad.status_code == 400
    good = await client.post(
        "/api/v1/auth/mfa/enable", json={"code": totp.totp_now(secret)}, headers=hdr
    )
    assert good.status_code == 200 and good.json()["mfa_enabled"] is True

    # Login now requires a code.
    no_code = await _login(client, "mfa@example.com", "secret-pass")
    assert no_code.status_code == 401
    with_code = await _login(client, "mfa@example.com", "secret-pass", totp.totp_now(secret))
    assert with_code.status_code == 200


@pytest.mark.asyncio
async def test_mfa_disable(client, session):
    await _make_user(session, email="d@example.com")
    token = await _token(client, "d@example.com", "secret-pass")
    hdr = {"Authorization": f"Bearer {token}"}
    secret = (await client.post("/api/v1/auth/mfa/setup", headers=hdr)).json()["secret"]
    await client.post("/api/v1/auth/mfa/enable", json={"code": totp.totp_now(secret)}, headers=hdr)

    dis = await client.post(
        "/api/v1/auth/mfa/disable", json={"code": totp.totp_now(secret)}, headers=hdr
    )
    assert dis.status_code == 200 and dis.json()["mfa_enabled"] is False
    # Login no longer needs a code.
    assert (await _login(client, "d@example.com", "secret-pass")).status_code == 200
