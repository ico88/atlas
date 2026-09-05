# Model & update operations

Practical guide for installing local AI, changing models, updating ATLAS and
recovering — without losing settings or data. (ROADMAP PR 2 + partial PR 3.)

## Manage models from the UI (no CLI)

The **Models** page lets you do it all from the browser:

- **Download a model** — type a name (e.g. `llama3.2:1b`) and click Download;
  progress is shown live (`POST /api/v1/models/pull`, background).
- **Set default** — pick the ⭐ default model used when a chat doesn't specify
  one (`POST /api/v1/models/default`); stored as a runtime setting (no restart).
- **Delete** an Ollama model (`DELETE /api/v1/models/{name}`).

And from the **Chat** page you can pick the model per conversation with the
model dropdown, or with the `/model <name>` and `/models` commands.

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
./atlas model-prune             # remove models except protected ones (--yes to skip prompt)
./atlas gpu-status              # detected vs configured backend + real GPU-in-use check
```

A new model becomes active **only after** a successful pull and smoke test; on
failure the previous model stays active. State is recorded in
`.atlas/state/models.env`. Pinning a version (`name:1b`) is preferred over
moving tags like `latest`.

### Pruning & GPU verification (PR 3)

`./atlas model-prune` frees disk by removing installed Ollama models **except the
protected ones**: the active model (`ATLAS_DEFAULT_MODEL`), the rollback-previous
model (from `.atlas/state/models.env`), and the embedding model
(`ATLAS_EMBEDDING_MODEL`). It lists what it will remove and asks to confirm
(`--yes` skips the prompt), then refreshes the registry.

`./atlas gpu-status` shows the host backend detected by the installer, the backend
ATLAS is actually configured to use for Ollama (from the generated compose
override), and — via `ollama ps` — whether a loaded model is really running on the
GPU. If it says CPU with a model that should be on the GPU, send one chat message
to load it and re-run.

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
