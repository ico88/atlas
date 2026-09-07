"""Internal PKI — CA issues client certs for mTLS (ROADMAP R5)."""

from __future__ import annotations

import pytest
from app.services import pki_service
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding


@pytest.mark.asyncio
async def test_issued_cert_is_signed_by_ca(session):
    ca_cert, _ = await pki_service.ensure_ca(session)
    issued = await pki_service.issue_cert(session, "node-worker-1")

    cert = x509.load_pem_x509_certificate(issued["cert_pem"].encode())
    # CN matches, issuer is the CA, and the CA public key verifies the signature.
    assert cert.subject.rfc4514_string() == "CN=node-worker-1"
    assert cert.issuer == ca_cert.subject
    ca_cert.public_key().verify(
        cert.signature,
        cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        cert.signature_hash_algorithm,
    )  # raises if invalid


@pytest.mark.asyncio
async def test_ca_is_stable_across_calls(session):
    a = await pki_service.ca_cert_pem(session)
    b = await pki_service.ca_cert_pem(session)
    assert a == b  # created once, then reused from the secret store


@pytest.mark.asyncio
async def test_revocation(session):
    issued = await pki_service.issue_cert(session, "node-2")
    serial = issued["serial"]
    assert serial not in await pki_service.revocation_list(session)
    assert await pki_service.revoke(session, serial) is True
    assert serial in await pki_service.revocation_list(session)
    assert await pki_service.revoke(session, "nonexistent") is False


@pytest.mark.asyncio
async def test_pki_api(client):
    ca = await client.get("/api/v1/pki/ca")
    assert ca.status_code == 200 and "BEGIN CERTIFICATE" in ca.json()["ca_pem"]

    issued = await client.post("/api/v1/pki/issue", json={"common_name": "node-x"})
    assert issued.status_code == 200
    body = issued.json()
    assert "BEGIN CERTIFICATE" in body["cert_pem"]
    assert "PRIVATE KEY" in body["key_pem"]
    serial = body["serial"]

    lst = await client.get("/api/v1/pki/certs")
    assert any(c["serial"] == serial for c in lst.json())

    rev = await client.post(f"/api/v1/pki/revoke/{serial}")
    assert rev.status_code == 200
    crl = await client.get("/api/v1/pki/crl")
    assert serial in crl.json()["revoked"]
