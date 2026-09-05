# ZeroTier Overlay Controller (ROADMAP PR 7)

The overlay network itself is set up by the **node installer** (PR 5): a node
installs ZeroTier, joins the network id, and reports its managed IP. This document
covers the optional **control-plane controller** that lets ATLAS list and
authorize a network's members from the UI/API.

## Off by default

With `ATLAS_ZEROTIER_CONTROLLER_ENABLED=false` (default), the control plane never
contacts ZeroTier Central — nodes still join via the installer and you authorize
members in the ZeroTier UI as usual. `GET /api/v1/zerotier/status` simply reports
`controller_enabled: false`.

## Enabling the controller

Set on the control plane:

- `ATLAS_ZEROTIER_CONTROLLER_ENABLED=true`
- `ATLAS_ZEROTIER_API_TOKEN=<ZeroTier Central API token>`
- `ATLAS_ZEROTIER_NETWORK_ID=<16-hex network id>`
- `ATLAS_ZEROTIER_AUTO_AUTHORIZE` — convenience flag surfaced in status (member
  auto-authorization policy).

Then the controller talks to the ZeroTier Central API
(`https://api.zerotier.com/api/v1`) with `Authorization: token …`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/zerotier/status` | controller state + member summary + counts |
| `GET`  | `/api/v1/zerotier/members` | the network's members (409 if disabled) |
| `POST` | `/api/v1/zerotier/members/{id}/authorize` | authorize/deauthorize (`{authorized}`) |

Member records are shaped by the pure `summarize_member` (id, name, authorized,
online, ip_assignments, last_seen). Every authorization change is **audited** in
the structured logs (`event: zt_authorize`, with member/network/authorized).

## UI

The **Nodes** page shows an *Overlay network — ZeroTier* card: when the controller
is enabled it lists members with their IP and online state and an
**Authorize / Deauthorize** button; when disabled it explains how to turn it on.

## Honest scope

The controller is a thin, guarded client over the ZeroTier Central API — it makes
a real call only when explicitly enabled and configured (tests cover the pure
shaping and the disabled path). Policy today is manual authorize + audit; an
auto-authorize-on-join loop can build on the same `authorize_member` primitive.
