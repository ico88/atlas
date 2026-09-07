# Security (ROADMAP R5 — Governed)

ATLAS is local-first and human-governed. Security features are off or open by
default for single-operator use, and tighten as you turn them on.

## Identity & access

- **RBAC** (`ATLAS_AUTH_ENFORCE=true`): `admin` / `user` roles. Off = open,
  single-operator (everyone acts as admin). See [USERS_RBAC.md](USERS_RBAC.md).
- **MFA (2FA)**: TOTP (RFC 6238), self-service on the **Security** page. Once
  enabled, login requires a 6-digit code. Compatible with Google Authenticator,
  Authy, 1Password.
- **Service accounts**: non-human API identities with scoped roles and revocable
  tokens (`atlas_sa_…`, only the hash is stored). Manage under
  `/api/v1/service-accounts`; authenticate with the `X-Service-Token` header.

## Secrets

- **Secret manager**: API keys/tokens are **encrypted at rest** (Fernet). The
  master key is `ATLAS_SECRET_KEY` (else derived from the JWT secret in dev).
  Listing never exposes plaintext; revealing a value is a separate, audited
  action. Admin UI on the Security page.

## PKI & transport

- **Internal CA**: issues client certificates for node **mTLS** from one trust
  root, with a served revocation list (`/api/v1/pki`: `ca`, `issue`, `certs`,
  `revoke`, `crl`). The CA key is kept encrypted in the secret store.
- Overlay transport hardening via ZeroTier / Caddy is complementary
  (see [ZEROTIER.md](ZEROTIER.md)).

## Auditability

- **Append-only audit log**: a SHA-256 **hash chain** makes it tamper-evident —
  any edit/deletion breaks the chain, detectable via `/api/v1/audit/verify`.
  Sensitive actions (model activation, node attach, MFA/secret/PKI/service-account
  changes) are recorded.

## Observability

- **SLOs & alerts**: `/api/v1/slo` reports task success rate, nodes-online ratio
  and control-plane health against targets; breaches show as alerts on the Admin
  hub.

## Supply chain

- **SBOM**: CI generates a CycloneDX SBOM for the Python dependencies
  (`infrastructure/scripts/sbom.sh`) and the frontend (`npm sbom`), uploaded as a
  build artifact.
- **Secret scanning**: Gitleaks runs over the full history in CI.
- **Image signing** (deploy-time, out of repo): sign the published container
  images with cosign and verify on the host; this is an operator step, documented
  here rather than enforced by the build.

## Honest scope

True HA of the auth/secret layer requires HA Postgres/Redis (see [HA.md](HA.md)).
The internal CA is a trust root for the ATLAS overlay, not a public PKI. Image
signing is a deploy-time control, not part of the repo's CI.
