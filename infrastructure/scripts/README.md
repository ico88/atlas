# Operational scripts

| Script | Purpose |
|--------|---------|
| `install.sh` | Install ATLAS prerequisites on **Ubuntu Server 24.04 LTS** (Docker Engine + Compose plugin, git, make, curl) and prepare `.env`. Idempotent. |

## Usage

From the repository root:

```bash
sudo ./infrastructure/scripts/install.sh
# or
make install
```

After it finishes (and after `newgrp docker` / re-login if you were added to the
`docker` group):

```bash
docker compose up --build   # or: make up
```

Future scripts (backup, hardware scan for the node agent, etc.) will live here.
