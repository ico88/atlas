# DeepSeek in Atlas and ALMA

Atlas supports DeepSeek through **local or remote Ollama** and through the
**official DeepSeek Cloud API**, without bundling an inference server. Both are
ordinary Atlas runtimes: ALMA uses the common gateway and a conversation can
change model between turns without losing its messages.

## Ollama on Ubuntu Server

Install Ollama on the inference host (which need not be the Atlas host) and pull a
model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull deepseek-r1:8b
sudo systemctl enable --now ollama
```

For remote access, bind Ollama to a private/VPN interface (for example with a
systemd override containing `Environment="OLLAMA_HOST=0.0.0.0:11434"`) and allow
TCP 11434 only from Atlas. Ollama has no built-in API authentication; never expose
that port directly to the Internet.

In **Runtimes**, add an `ollama` runtime with an endpoint such as
`http://10.0.0.20:11434`, then click **Discover models**. Atlas calls `/api/tags`,
registers the advertised models/deployments, and exposes them in ALMA's selector.
Replies use `/api/chat` streaming. Connection failures and read timeouts become
actionable errors and the gateway can select another healthy deployment.

The simple single-runtime setup also remains supported:

```dotenv
ATLAS_OLLAMA_URL=http://10.0.0.20:11434
ATLAS_DEFAULT_MODEL=deepseek-r1:8b
```

## DeepSeek Cloud

1. Set a unique `ATLAS_SECRET_KEY` (a Fernet key) through the deployment's secret
   manager or untracked `.env` file.
2. Set `ATLAS_ROUTING_CLOUD_ALLOWED=true`. `LOCAL_ONLY` policies still prohibit
   every cloud runtime.
3. In **Runtimes**, create a `deepseek` runtime. Leave the endpoint blank for
   `https://api.deepseek.com` and enter the API key in the password field.
4. Click **Discover models**, then select a returned model such as
   `deepseek-chat` or `deepseek-reasoner` in ALMA.

API keys are encrypted before persistence, omitted from all read schemas, and
decrypted only in memory when constructing an adapter. Never commit credentials.

## Verification

Automated tests mock HTTP and need neither Ollama nor a cloud key. Live checks are
manual and require operator infrastructure:

```bash
curl "$OLLAMA_URL/api/tags"
curl -H "Authorization: Bearer $DEEPSEEK_API_KEY" https://api.deepseek.com/v1/models
```

After discovery, start an ALMA conversation, choose each provider-labelled model,
and verify that tokens arrive incrementally.
