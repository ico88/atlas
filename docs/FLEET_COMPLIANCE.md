# Fleet Compliance & Auto-Remediation (ROADMAP PR 24 / PR 25)

One page, one glance, one click. Declare the desired fleet state, see drift, and
fix it — safely.

## Desired state (PR 24)

An operator setting (`fleet_desired`, stored via the settings service — no
migration) with three fields:

- `target_version` — the version every node should run;
- `required_capabilities` — capabilities every node must advertise;
- `min_online` — the minimum number of online nodes the fleet must keep.

`GET/PUT /api/v1/fleet/desired` reads/writes it.

## Drift (PR 24)

`compute_drift` (pure) compares the live inventory against the desired state and
returns, per node: `online`, `quarantined`, `version`, `compliant`, and an
`issues` list (`offline`, `version X != Y`, `missing capability: …`,
`quarantined`). The fleet summary carries `total`, `online`, `quarantined`,
`compliant`, `drifted`, `compliance_pct` and `meets_min_online`.

`GET /api/v1/fleet/compliance` returns the report with a guided **diagnosis** and
a **recommended action** attached to each node.

## Remediation (PR 25)

`diagnose` (pure) maps a node's drift to a remedy:

| Situation | Diagnosis | Recommended | Auto? |
|-----------|-----------|-------------|-------|
| version drift (online) | running a different version | **remediate** | ✅ safe |
| offline | can't fix remotely | quarantine | human |
| missing capability | reconfigure the agent | — | human |
| quarantined | excluded from scheduling | reinstate | human |

- **remediate** sets the node's `desired_version` to the fleet target (the agent
  applies it and reports back);
- **quarantine** sets `nodes.quarantined = true` — the scheduler then refuses to
  hand it work (`claim_task` returns nothing);
- **reinstate** clears it.

`POST /api/v1/fleet/remediate` performs one action; `POST
/api/v1/fleet/auto-remediate` applies the *safe* one (version re-align) to every
drifted online node and leaves offline/capability cases for a human. Every action
is recorded in `remediation_events` (migration 0021), listed at
`GET /api/v1/fleet/remediation-events`.

## UI

The **Fleet Health** page shows a compliance %, live counters and the min-online
check; a desired-state editor; and a node table where each drifted node carries
its diagnosis and one-click **Remediate / Quarantine / Reinstate**, plus an
**Auto-remediate now** button. It auto-refreshes.

## Honest scope

Remediation drives the node via `desired_version` and the quarantine flag; the
actual self-update happens on the agent. Diagnosis is rule-based (not a model).
