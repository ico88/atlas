# Control-Plane HA (ROADMAP PR 9)

Run more than one control-plane instance so the loss of one does not stop
coordination. The instances elect a **leader** through a short-lived Redis lease;
only the leader runs singleton background work, and if it dies another instance
takes over automatically.

## Leader election

- The leader holds `atlas:ha:leader` (value = its instance id) with a TTL of
  `ATLAS_HA_LEASE_TTL` seconds. The leader renews it well within the TTL.
- A non-leader can only take the lease when it is **free** — so at most one leader
  exists at a time.
- If the leader stops renewing (crash, network partition from Redis), the lease
  **expires** and the next instance to try wins: automatic failover within
  `ATLAS_HA_LEASE_TTL`.
- Each instance also writes a heartbeat key `atlas:ha:member:<id>` so the cluster
  members are visible.

Singleton work (today: the autonomous improvement proposer) checks
`leadership_service.is_leader()` before acting, so it runs on exactly one
instance. Request handling, chat, and the API are **stateless** and run on every
instance behind a load balancer.

## Single-node (default)

With `ATLAS_HA_ENABLED=false` there is no election: the one instance is always the
leader and behaviour is unchanged. Turn HA on only when you run multiple
instances against **shared** Postgres and Redis.

## Status

`GET /api/v1/cluster` returns the mode, this instance's id, the current leader,
and the members list. The **System Status** page shows the same, with a leader
badge.

## Deploying multiple instances

1. Point every instance at the **same** Postgres and Redis
   (`ATLAS_DATABASE_URL`, `ATLAS_REDIS_URL`).
2. Give each a stable `ATLAS_INSTANCE_ID` (defaults to `host-pid`).
3. Set `ATLAS_HA_ENABLED=true` on all of them.
4. Put a load balancer / virtual endpoint in front (round-robin over the
   stateless API; `/health` for liveness).

## Honest scope & DR

This is single-Redis / single-Postgres coordination: the election is correct as
long as that Redis is reachable. **True HA requires the data layer itself to be
highly available** — a Postgres primary/replica with failover and a Redis with
replication/Sentinel — which is infrastructure outside this repo. For disaster
recovery, `./atlas backup` captures `.env` + a DB dump before every update; ship
those off-box and restore onto a fresh host, then bring instances up against the
restored data layer.
