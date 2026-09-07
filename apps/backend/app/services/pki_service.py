"""Internal PKI — a small CA that issues node client certs for mTLS (R5).

The CA private key + certificate are created on first use and kept **encrypted**
in the secret store (via ``secret_service``). ``issue_cert`` mints a short-lived
client certificate signed by the CA and returns it with its private key once
(never stored). Issued certs are recorded so they can be listed and revoked.

Honest scope: this is an internal CA for the ATLAS overlay, not a public PKI. It
complements the mTLS enrollment (PR 6): the CA here is the trust root, revocation
is a served list of serials (checked by the control plane), not a full X.509 CRL.
"""

from __future__ import annotations

import datetime as dt
import logging

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pki import IssuedCert
from app.services import secret_service

logger = logging.getLogger(__name__)

_CA_KEY = "pki.ca_key"
_CA_CERT = "pki.ca_cert"
_UTC = dt.UTC


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _key_pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _cert_pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def ensure_ca(session: AsyncSession) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Return the CA cert + key, creating and storing them on first use."""

    cert_pem = await secret_service.get_secret(session, _CA_CERT)
    key_pem = await secret_service.get_secret(session, _CA_KEY)
    if cert_pem and key_pem:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        return cert, key  # type: ignore[return-value]

    key = _new_key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ATLAS Internal CA")])
    now = dt.datetime.now(_UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    await secret_service.set_secret(session, name=_CA_KEY, value=_key_pem(key))
    await secret_service.set_secret(session, name=_CA_CERT, value=_cert_pem(cert))
    logger.info("internal CA created", extra={"event": "pki_ca_created"})
    return cert, key


async def ca_cert_pem(session: AsyncSession) -> str:
    cert, _ = await ensure_ca(session)
    return _cert_pem(cert)


async def issue_cert(
    session: AsyncSession, common_name: str, *, days: int = 365
) -> dict[str, str]:
    """Issue a client cert for ``common_name`` signed by the CA. Returns PEMs."""

    ca_cert, ca_key = await ensure_ca(session)
    key = _new_key()
    now = dt.datetime.now(_UTC)
    not_after = now + dt.timedelta(days=days)
    serial = x509.random_serial_number()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - dt.timedelta(minutes=1))
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    session.add(
        IssuedCert(serial=str(serial), common_name=common_name, not_after=not_after)
    )
    await session.commit()
    logger.info(
        "certificate issued",
        extra={"event": "pki_issue", "context": {"cn": common_name, "serial": str(serial)}},
    )
    return {
        "common_name": common_name,
        "serial": str(serial),
        "cert_pem": _cert_pem(cert),
        "key_pem": _key_pem(key),
        "ca_pem": _cert_pem(ca_cert),
    }


async def list_certs(session: AsyncSession) -> list[IssuedCert]:
    rows = await session.execute(select(IssuedCert).order_by(IssuedCert.created_at.desc()))
    return list(rows.scalars().all())


async def revoke(session: AsyncSession, serial: str) -> bool:
    row = (
        await session.execute(select(IssuedCert).where(IssuedCert.serial == serial))
    ).scalar_one_or_none()
    if row is None:
        return False
    row.revoked = True
    await session.commit()
    return True


async def revocation_list(session: AsyncSession) -> list[str]:
    rows = await session.execute(
        select(IssuedCert.serial).where(IssuedCert.revoked.is_(True))
    )
    return [r[0] for r in rows.all()]
