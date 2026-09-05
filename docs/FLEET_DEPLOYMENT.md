# Fleet Update & Safe Deployment (ROADMAP PR 21 / PR 22)

Roll a target version out across the node fleet **safely**: a small canary wave,
a **health gate** before promoting the rest, a rolling wave, and automatic
**rollback** on any failure. Planning and the gate logic are pure functions, so
wave selection and rollback are unit-tested without a live fleet.

## Lifecycle

```
create → CANARY  (canary nodes told to update; rollout nodes PENDING)
   nodes report ──▶ health gate on /advance:
        canary all HEALTHY → promote rollout ──▶ ROLLING
        any canary FAILED  → revert everyone ──▶ ROLLED_BACK
ROLLING → nodes report ──▶ /advance:
        rollout all HEALTHY → COMPLETED
        any FAILED          → ROLLED_BACK
```

## Planning (PR 21)

`plan_targets` classifies every node at creation time:

- **offline** → `SKIPPED_OFFLINE` (reconciled on a later deployment when back online);
- current version **below the compatibility floor** (`min_compatible`) →
  `INCOMPATIBLE` (skipped with a reason);
- otherwise **eligible** — the first `canary_count` form the **canary** wave, the
  rest the **rollout** wave.

Compatibility uses a numeric version compare (`v1.2.3` → `(1,2,3)`); a node with no
reported version, or no floor set, is treated as compatible.

## How a node actually updates

The control plane sets `node.desired_version`; the node agent applies it and
reports the result (new `version` + health) on its next heartbeat. `POST
/deployments/{id}/report` records that report (`HEALTHY` when the node is on the
target version and healthy, else `FAILED`). `POST /deployments/{id}/advance`
applies the health gate and moves the rollout forward — or rolls back.

## Safe deployment (PR 22)

- **Health gate**: the rollout wave is only told to update after every canary node
  is `HEALTHY`.
- **Rollback**: any `FAILED` report at the gate (canary or rollout) reverts every
  touched node's `desired_version` to its `from_version` and marks the deployment
  `ROLLED_BACK`. Skipped nodes are never touched.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/deployments` | plan + start (`target_version`, `canary_count`, `min_compatible`) |
| `GET`  | `/api/v1/deployments` | list |
| `GET`  | `/api/v1/deployments/{id}` | full state (targets per wave) |
| `POST` | `/api/v1/deployments/{id}/report` | a node's post-update report |
| `POST` | `/api/v1/deployments/{id}/advance` | apply the health gate / promote / roll back |

Migration `0020` adds `deployments`, `deployment_targets` and `nodes.desired_version`.

## UI

The **Fleet Update** page starts a rollout (target version, canary size, optional
compatibility floor), shows each wave's nodes and statuses, auto-refreshes while
in flight, and offers **Advance / health-gate**.

## Honest scope

The node agent side (reading `desired_version`, self-updating, reporting) is the
integration point; this PR delivers the control-plane orchestration, the gate, and
rollback, all tested. Real end-to-end update of a physical node depends on the
agent honoring `desired_version`.
