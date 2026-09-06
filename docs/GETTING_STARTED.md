# Get started — the easy path

ATLAS is powerful under the hood (multi-runtime, nodes, policies), but a normal
user should never have to touch any of that to get going. The **Get Started**
page (`/setup`) does it for you.

## Two clicks

1. Open **Get Started** (top of the sidebar).
2. It detects your machine (CPU / RAM / GPU) and **recommends a model** that fits.
3. Click **Install & activate** on the recommended model.

That's it. ATLAS downloads the model and, on success, **auto-configures** everything:

- creates a local Ollama **runtime** (`local-ollama`);
- creates a **deployment** of the model on it;
- points the **`atlas.general`** alias at it and sets it as the **default**.

Open **Chat** and start talking — the Model Gateway routes to the model you just
activated. Already-installed models show **Activate** instead (no re-download).

## Auto-configuration everywhere

The same auto-wiring runs whenever a model is pulled — from Get Started *or* the
Models page. You never have to fill in runtimes, deployments or aliases by hand;
the advanced **AI Runtimes** page is there only if you *want* fine control
(multiple runtimes, remote nodes, cloud, routing policies).

## If the AI engine isn't running

If the page says the local engine (Ollama) isn't running, start it with:

```
docker compose --profile ai up -d
```

then reload Get Started.

## API (for automation)

- `GET /api/v1/setup/status` — hardware, recommendation, installed/active model.
- `POST /api/v1/setup/install {model}` — download then auto-activate.
- `POST /api/v1/setup/activate {model}` — activate an already-installed model.
