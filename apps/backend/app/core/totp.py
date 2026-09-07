"""TOTP (RFC 6238) — dependency-free MFA (ROADMAP R5).

Pure standard-library implementation so multi-factor auth needs no extra package
and is fully unit-tested. Compatible with Google Authenticator / Authy / 1Password
(SHA-1, 6 digits, 30-second period).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_DIGITS = 6
_PERIOD = 30


def generate_secret(length: int = 20) -> str:
    """A new random base32 secret (no padding), as shown in authenticator apps."""

    return base64.b32encode(secrets.token_bytes(length)).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    # Base32 decode (restore padding, uppercase).
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**_DIGITS)
    return str(code).zfill(_DIGITS)


def totp_now(secret: str, at: float | None = None) -> str:
    """The current TOTP code for a secret."""

    now = int(at if at is not None else time.time())
    return _hotp(secret, now // _PERIOD)


def verify(secret: str, code: str, *, at: float | None = None, window: int = 1) -> bool:
    """Verify a code, tolerating +/- ``window`` periods of clock skew."""

    if not secret or not code or not code.isdigit():
        return False
    now = int(at if at is not None else time.time())
    counter = now // _PERIOD
    for drift in range(-window, window + 1):
        c = counter + drift
        if c < 0:  # avoid negative counters near the epoch (tests)
            continue
        if hmac.compare_digest(_hotp(secret, c), code):
            return True
    return False


def provisioning_uri(secret: str, account: str, issuer: str = "ATLAS") -> str:
    """otpauth:// URI for a QR code / manual entry in an authenticator app."""

    label = f"{quote(issuer)}:{quote(account)}"
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={_DIGITS}&period={_PERIOD}"
    )
