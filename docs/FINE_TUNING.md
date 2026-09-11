# Fine-tuning locale (self-improvement)

ATLAS già si auto-migliora **entro i guardrail**: proposer autonomo → esperimenti
A/B → routing adattivo dalle eval → canary con health gate e rollback. Tutto
questo **seleziona e configura** il modello migliore tra quelli che ha, ma non
cambia il modello. Il fine-tuning è il passo che permette ad ATLAS di
**migliorare il modello stesso** dalle proprie buone interazioni — in locale,
senza inviare dati da nessuna parte.

> Il tetto di intelligenza resta il modello di base: il fine-tuning adatta il
> modello al **tuo** dominio e stile, non lo trasforma in un modello più grande.

## Pipeline

```
feedback 👍  ──►  dataset (curato)  ──►  export JSONL  ──►  training LoRA (nodo GPU)  ──►  adozione (eval + canary)
   chat            prompt→response         chat format        adapter                       diventa default solo se vince
```

1. **Curazione** — ogni risposta dell'assistente con feedback positivo (👍,
   `rating ≥ 1`) diventa un esempio `prompt → response` (il prompt è il turno
   utente immediatamente precedente). Deduplica per hash del contenuto. Si
   possono anche aggiungere esempi a mano ed escludere quelli non desiderati.
   - Servizio: `finetune_service.curate_from_feedback` / `add_example`.
2. **Export** — gli esempi *inclusi* sono resi in JSONL in formato chat
   (`{"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}`), il
   formato di training più diffuso. Funzione pura e testata: `build_jsonl`.
3. **Training** — un job addestra un **adapter LoRA** per un modello base. Il
   control plane **non addestra mai**: dispatcha un task `fine_tune` (capability
   richiesta `gpu`) a un nodo. L'executor del node-agent:
   - se `payload.simulate` è vero → dry-run deterministico (metriche simulate),
     per provare la pipeline end-to-end **senza GPU**;
   - altrimenti richiede un trainer reale via `ATLAS_TRAIN_CMD` sul nodo;
   - se non c'è né l'uno né l'altro **fallisce esplicitamente** (non finge un
     successo).
4. **Adozione** — un job completato non scavalca nulla: `adopt_job` crea una
   **proposta di miglioramento** con l'adapter come candidato. Da lì valgono gli
   **stessi guardrail** di qualunque altro cambio: deve battere la baseline su
   una suite di eval e superare l'**health gate del canary** prima di diventare
   default (o fare auto-rollback).

## API

| Metodo | Endpoint | Cosa fa |
|---|---|---|
| GET | `/api/v1/finetune/readiness` | GPU disponibile? quanti feedback positivi? |
| POST | `/api/v1/finetune/datasets` | crea un dataset |
| GET | `/api/v1/finetune/datasets` | elenca i dataset |
| POST | `/api/v1/finetune/datasets/{id}/curate` | raccoglie dai feedback positivi |
| GET | `/api/v1/finetune/datasets/{id}/examples` | elenca gli esempi |
| POST | `/api/v1/finetune/datasets/{id}/examples` | aggiunge un esempio a mano |
| PATCH | `/api/v1/finetune/examples/{id}` | includi/escludi un esempio |
| GET | `/api/v1/finetune/datasets/{id}/export` | scarica il JSONL di training |
| POST | `/api/v1/finetune/jobs` | dispatcha un training LoRA su nodo GPU |
| GET | `/api/v1/finetune/jobs` | stato dei job (loss, esempi, errori) |
| POST | `/api/v1/finetune/jobs/{id}/adopt` | crea la proposta (eval + canary) |

UI: pagina **Fine-tuning** (sezione *Govern* della sidebar).

## Requisiti hardware — onestà

Il fine-tuning reale richiede una **GPU** e un trainer. Sull'hardware solo-CPU
la parte di *raccolta, curazione, export e gating* funziona comunque (è
indipendente dall'hardware); il passo di **training** attende un nodo con
capability `gpu` — oppure usa `simulate=true` per verificare l'intera pipeline
senza addestrare davvero. Per abilitare il training vero su un nodo, imposta
`ATLAS_TRAIN_CMD` con il comando del trainer (riceve il JSONL su stdin e deve
stampare una riga JSON finale con almeno `model` e, opzionalmente, `metrics`);
le variabili `ATLAS_FT_BASE_MODEL`, `ATLAS_FT_ADAPTER_NAME`, `ATLAS_FT_EPOCHS`
sono passate nell'ambiente.
