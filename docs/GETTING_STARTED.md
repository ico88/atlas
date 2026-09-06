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

## Adding a worker node — guided, step by step

On the node machine, run the installer as a node; it walks you through it and
**checks each step**:

```
sudo ./infrastructure/scripts/install.sh --role node
```

1. **Install the node** — base packages, Docker, the node agent.
2. **Configure ZeroTier** — join the overlay network; the installer waits until
   the controller **authorizes** this node (you authorize it in ZeroTier Central
   or from the ATLAS Nodes page) and then derives the node's overlay IP.
3. **Find the control plane** — it autodiscovers the manager over the overlay;
   if it can't, it **asks you for the manager's ZeroTier IP** (manual callback)
   and verifies reachability. On a plain LAN (no ZeroTier) it scans for the
   manager and offers what it finds.
4. **Approve the node** — approve the enrollment on the control plane (ATLAS
   Nodes page); the installer then confirms the real **MATCH** — the node has
   registered and is visible to the manager.
5. **Model & updates** — assign/download a model to the node from the **Nodes**
   page (one click), and roll out node updates from **Fleet**.

The corresponding one-shot from the ATLAS UI is the **Add a node** wizard
(Fleet › Nodes), which mints the token, shows the exact node `.env`, authorizes
the ZeroTier member, approves the node, and attaches a model — the same steps,
driven from the manager.
