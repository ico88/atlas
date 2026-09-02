# Model & update operations

Practical guide for installing local AI, changing models, updating ATLAS and
recovering — without losing settings or data. (ROADMAP PR 2 + partial PR 3.)

## What is preserved

- **Settings** — `.env` is git-ignored, so `git pull` / updates never overwrite
  it. `./atlas update` also copies it into `.atlas/backups/<timestamp>/`.
- **Data & memory** — PostgreSQL (tasks, conversations, memory, RAG chunks,
  maintenance, escalations), Redis and Ollama models live in **named Docker
  volumes** (`pgdata`, `redisdata`, `ollamadata`). `docker compose up` preserves
  them; only `docker compose down -v` would delete them — the updater never does.
- A **PostgreSQL dump** is taken before every `./atlas update`.

## Install local AI

```bash
# Interactive (asks: enable Ollama? which model? embeddings?)
sudo ./infrastructure/scripts/install.sh

# Non-interactive
sudo ./infrastructure/scripts/install.sh --role control-plane \
     --with-ollama --ollama-model llama3.2 --yes

# With Ollama embeddings for RAG
sudo ./infrastructure/scripts/install.sh --with-ollama \
     --ollama-model llama3.2 --with-ollama-embeddings \
     --embedding-model nomic-embed-text --yes
```

## GPU backends

Auto-detection order: **NVIDIA → ROCm → Vulkan → CPU**. Override with `--gpu`:

| Flag | Meaning |
|------|---------|
| `--gpu auto` | detect (default) |
| `--gpu nvidia` | NVIDIA (nvidia-container-toolkit) |
| `--gpu rocm` | AMD ROCm |
| `--gpu vulkan` | experimental Vulkan (AMD cards without ROCm) |
| `--gpu cpu` | force CPU |
| `--allow-experimental-gpu` | auto-select Vulkan without prompting |
| `--allow-cpu-fallback` | allow CPU when a requested GPU is missing |

The installer writes `.atlas/docker-compose.gpu.yml` (not committed). For AMD
Vulkan it maps `/dev/dri`, `/dev/kfd`, adds the `video`/`render` groups (GIDs
resolved dynamically) and sets `OLLAMA_VULKAN=1`. All compose commands
(`up`, model pull, update) include this override automatically.

### Requirements / disk & RAM

- Models are downloaded into the `ollamadata` volume — ensure free disk (a small
  model like `llama3.2:1b` is ~1 GB; larger models need several GB).
- For legacy/low-VRAM GPUs prefer a small model (e.g. `llama3.2:1b`).

## Change / roll back a model

```bash
./atlas model-update llama3.3   # pull -> smoke test -> activate (keeps previous)
./atlas model-rollback          # revert to the previous model
./atlas model-list              # installed models + active one
```

A new model becomes active **only after** a successful pull and smoke test; on
failure the previous model stays active. State is recorded in
`.atlas/state/models.env`. Pinning a version (`name:1b`) is preferred over
moving tags like `latest`.

## Update everything

```bash
./atlas update          # backup -> pull -> rebuild -> migrate -> health check
./atlas update-status   # show the last update log
./atlas backup          # on-demand settings + DB backup
```

## Troubleshooting

- **`gpu: null` / CPU only** — check `GET /api/v1/system/hardware`
  (`recommended_ollama_backend`). Confirm `/dev/dri/renderD*` exists and the user
  is in the `render`/`video` groups (re-login after being added).
- **Ollama not ready** — `docker compose --profile ai logs ollama`; re-pull with
  `./atlas model-update <model>`.
- **Manual recovery of a model** — `docker compose exec ollama ollama pull <m>`
  then `./atlas model-list`.
- **Port already in use** — set `ATLAS_HTTP_PORT` in `.env` and re-run
  `docker compose up -d`.
