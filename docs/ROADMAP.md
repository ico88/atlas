# ATLAS — Piano completo di sviluppo e implementazione

> Documento unico di riferimento per evolvere ATLAS da bootstrap locale a
> piattaforma distribuita, resiliente, governata e progressivamente adattiva.
> Comprende Ollama, GPU, nodi, ZeroTier, memoria, ambienti, web, aggiornamenti,
> autoriparazione, sicurezza e operazioni.

> Questo documento è la continuazione dei milestone della specifica (§16):
> definisce l'evoluzione da bootstrap a prodotto distribuito, organizzata per
> **release R1–R7** e **PR 1–26**. Vedi [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
> per lo stato dei milestone.

## Punto di partenza: milestone M0–M10 (spec §16)

I milestone hanno costruito la piattaforma; le release R1–R7 la induriscono a
prodotto. Stato attuale:

| Milestone | Stato | Confluisce in |
|-----------|-------|---------------|
| M0 Repository bootstrap | ✅ done | base di tutte le release |
| M1 Foundation (+ auth JWT) | ✅ done | **R5** (RBAC/MFA/PKI estendono l'auth) |
| M2 Local AI (Ollama, chat, registry, hw scan) | ✅ done | **R1** (lifecycle Ollama + GPU discovery) |
| M3 Task Engine (queue, retry, DAG, scheduler) | ✅ done | **R3** (query/coda) + **R2** (scheduler resiliente) |
| M4 Node Federation (register/heartbeat, remote exec) | ✅ done | **R2** (enrollment UI, ZeroTier, fleet) |
| M5 ALMA (decomposizione DAG, aggregazione) | ✅ done | **R3** (background/coda) + **R6** |
| M6 Maintenance Core (dry-run, approval gate) | ✅ done | **R6** (self-healing reale, canary) |
| M7 Manual Escalation (ChatGPT/Claude) | ✅ done | **R5/R6** (revisione critica, provider) |
| M8 RAG/Memory (embeddings, citazioni) | ✅ done | **R3** (memoria/ambienti) + **R4** (web) |
| M9 Optional Cloud (LiteLLM, OpenAI/Anthropic) | ⬜ | consegnato con **R1/R5** nell'AI Router |
| M10 Optimization (router learning, eval) | ⬜ | consegnato con **R5 evals** + **R6** |

Mappa sintetica release → milestone: R1←M2 · R2←M4 · R3←M3+M5+M8 · R4←M8(nuovo web)
· R5←M1+M6 · R6←M6 · R7←nuovo (HA).

## Obiettivo

Rendere Ollama parte del ciclo operativo standard di ATLAS:

- l'installazione del control plane deve poter abilitare Ollama, scaricare il modello scelto, configurarlo e verificarlo;
- un aggiornamento successivo del modello deve avvenire con un solo comando, senza modifiche manuali a `.env`;
- ogni operazione deve essere idempotente, osservabile e reversibile;
- in caso di errore ATLAS deve conservare il modello precedente e continuare a funzionare.

Il repository dispone già del servizio Compose `ollama`, del profilo `ai`, di `ATLAS_OLLAMA_URL`, `ATLAS_DEFAULT_MODEL`, del model registry e del fallback `echo`. Il lavoro riguarda soprattutto automazione, validazione e ciclo di aggiornamento.

## Roadmap per release

Lo sviluppo procede per prodotti funzionanti e verificabili, non come un unico
rilascio contenente tutte le funzionalità.

### R1 — Local Reliable
Installer completo; Ollama e scelta modello; rilevamento CPU/RAM/GPU
AMD/NVIDIA/Vulkan; chat e streaming verificati; model update e rollback;
dashboard risorse locale; backup e restore di base; updater transazionale;
diagnostica e modalità recovery.
Uscita: installazione pulita e upgrade producono un sistema funzionante senza
comandi successivi.

### R2 — Distributed
Node Setup UI; ZeroTier e Network ID; enrollment dalla UI e mTLS; scheduler con
lease, fencing e checkpoint; drain, quarantena e failover; metriche multi-nodo;
aggiornamento rolling della flotta; conformità e autoriparazione iniziale.
Uscita: la perdita di un worker non interrompe i nodi sani né perde task
trasferibili.

### R3 — Workspace
Ambienti e manifest; memoria controllabile; conversazioni e coda di messaggi;
query interrompibili e in background; artifact store; snapshot, export e restore;
isolamento e permessi.
Uscita: un progetto può essere abbandonato e ripreso senza ricostruire il
contesto.

### R4 — Connected
Ricerca web e fetch controllato; protezioni SSRF e prompt injection; ranking e
citazioni; cache e budget; capability web sui nodi; privacy e modalità offline.
Uscita: ogni risposta web è tracciabile e supportata da fonti consultabili.

### R5 — Governed
RBAC, MFA e account di servizio; secret manager e PKI completa; audit
append-only; eval e baseline; revisione critica multi-modello; SLO, alert e
report; supply-chain security.
Uscita: azioni, dati e decisioni sono autorizzati, valutati e auditabili.

### R6 — Adaptive
Provider GitHub reale e sandbox; patch, test e PR automatiche ma governate;
esperimenti A/B; Continuous Improvement; canary, health gate e rollback;
diagnosi collaborativa con l'utente.
Uscita: ATLAS può proporre e verificare miglioramenti senza applicarli fuori dai
guardrail o senza approvazione.

### R7 — Highly Available
Control plane replicato; PostgreSQL e coda altamente disponibili; leader
election e fencing; endpoint virtuale; backup fuori sito; prove automatiche di
failover e disaster recovery.
Uscita: la perdita di un'istanza del control plane non interrompe coordinamento
e accesso al prodotto.

## Dipendenze e ordine di realizzazione

```text
Sicurezza, versionamento e backup
              |
              v
R1 Local Reliable
              |
              v
R2 Distributed -----> telemetria e fleet updater
              |
              v
R3 Workspace -------> memoria, background e artefatti
              |
              v
R4 Connected -------> web controllato e citazioni
              |
              v
R5 Governed --------> eval, audit e revisione critica
              |
              v
R6 Adaptive --------> self-healing e miglioramento
              |
              v
R7 Highly Available
```

Self-healing reale non deve precedere backup, sandbox, audit ed eval. Il fleet
updater non deve precedere updater locale e rollback. Il control plane HA deve
essere affrontato dopo avere stabilizzato protocolli, database e recovery.

## Suddivisione consigliata del lavoro (PR)

Stato: ✅ = consegnata.

1. ✅ **PR 1 — Hardware discovery:** scanner NVIDIA/AMD/Vulkan/ROCm/DRM in
   `apps/backend/app/core/hardware.py`, parser puri e testati, `GET
   /api/v1/system/hardware` con struttura `gpu.devices[]` + `recommended_ollama_backend`,
   esclusione dei software renderer (`llvmpipe`). UI Models mostra GPU e backend.
2. ✅ **PR 2 — Installer:** opzioni CLI (`--with-ollama`, `--ollama-model`,
   `--gpu ...`), profilo `ai`, override GPU generato (`.atlas/docker-compose.gpu.yml`),
   configurazione `.env`, pull + readiness + smoke test. Libreria shell condivisa
   (`infrastructure/scripts/lib/`). Vedi [MODEL_OPERATIONS.md](MODEL_OPERATIONS.md).
3. ✅ **PR 3 — Model lifecycle:** `./atlas model-update`/`model-rollback` atomici
   con smoke test e stato in `.atlas/state/models.env`; **`model-prune`**
   protetto (mantiene attivo + rollback-precedente + embedding) e **`gpu-status`**
   (backend rilevato vs configurato + verifica reale via `ollama ps`). Helper puri
   testati (`models_to_prune`, `gpu_backend_configured`). Vedi
   [MODEL_OPERATIONS.md](MODEL_OPERATIONS.md).
4. **PR 4 — Operations:** pruning protetto, Makefile, logging e documentazione.
5. ✅ **PR 5 — Node Setup UI:** UI locale di stato/diagnostica servita dal node
   agent (identità, hardware, capabilities, rete/ZeroTier, raggiungibilità del
   control plane) su `127.0.0.1:8971`, con codice bootstrap monouso per le
   azioni protette (`/api/reenroll`). Installer node con
   `--network-provider zerotier --zerotier-network-id <16-hex>` (installa
   ZeroTier sull'host, join alla rete, stampa node id + IP gestito) e
   `--await-enrollment`. Parser ZeroTier puri e testabili.
6. ✅ **PR 6 — Node enrollment:** credenziali per-nodo con gate di approvazione
    (`node_enrollments`, migrazione 0010) — invito (token monouso, salvato solo
    come hash SHA-256), stati PENDING→APPROVED/REJECTED/REVOKED, rotazione e
    revoca. Register/heartbeat consentiti da PENDING, claim solo se APPROVED;
    enforcement opt-in (`ATLAS_NODE_ENROLLMENT_REQUIRED`, off di default). API
    `/api/v1/enrollments` + sezione Enrollment nella pagina Nodes. mTLS resta
    hardening di trasporto complementare (Caddy/ZeroTier). Vedi
    [NODE_ENROLLMENT.md](NODE_ENROLLMENT.md).
7. **PR 7 — ZeroTier integration:** stato, policy, API controller opzionale e audit.
8. ✅ **PR 8 — Resilient scheduler:** lease temporizzato + fencing token sui task
    RUNNING (worker locale e claim nodo), heartbeat/checkpoint per ripresa,
    `reclaim_expired` (failover: locali→RETRYING ri-accodati, remoti→QUEUED,
    esauriti→FAILED, token ruotato), rifiuto dei risultati tardivi (409).
    Migrazione 0012; config `ATLAS_TASK_LEASE_SECONDS`/
    `ATLAS_SCHEDULER_RECLAIM_ENABLED`. Vedi
    [RESILIENT_SCHEDULER.md](RESILIENT_SCHEDULER.md).
9. **PR 9 — Control plane HA:** replica, leader election e disaster recovery.
10. ✅ **PR 10 — Query lifecycle:** modello `queries`/`query_events` (migrazione
    0008), esecuzione in background con proprio session, stati
    PENDING→RUNNING→COMPLETED/FAILED/CANCELLED, cancellazione cooperativa (flag
    Redis controllato ad ogni token, risultato parziale salvato), heartbeat e
    recovery all'avvio (RUNNING orfani ri-accodati). API
    `POST/GET /api/v1/queries`, `GET /api/v1/queries/{id}` (con eventi),
    `POST /api/v1/queries/{id}/cancel`. Vedi
    [QUERY_LIFECYCLE.md](QUERY_LIFECYCLE.md).
11. ✅ **PR 11 — Conversation queue:** coda messaggi per-conversazione in Redis —
    invio immediato quando idle, accodamento FIFO quando occupata, merge dei
    messaggi utente consecutivi in coda (`merged_count`), lock per-conversazione
    (un turno alla volta) e parallelismo globale limitato
    (`ATLAS_CONVERSATION_MAX_PARALLEL`). API
    `POST /api/v1/conversations/{id}/messages`,
    `GET …/queue`, `POST …/queue/complete`. Vedi
    [CONVERSATION_QUEUE.md](CONVERSATION_QUEUE.md).
12. ✅ **PR 12 — Resource telemetry:** `node_metrics` (migrazione 0013) ingeriti
    dagli heartbeat (load/RAM + campi extra), storico per-nodo con retention
    (`ATLAS_METRICS_HISTORY_LIMIT`), performance Ollama aggregata dai messaggi
    (count/avg/min/max latenza). API `/api/v1/metrics/nodes[/{id}]` e
    `/metrics/ollama` + pagina **Resources**. Vedi
    [RESOURCE_TELEMETRY.md](RESOURCE_TELEMETRY.md).
13. ✅ **PR 13 — Environments:** workspace isolati con manifest + variabili
    (`environments`, `environment_snapshots`, migrazione 0014), scoping di
    task/query/memory via `environment_id` (colonne + filtri), snapshot e restore
    a livello di configurazione (con summary stats). API `/api/v1/environments`
    (+ snapshots/restore) e pagina **Environments**. Vedi
    [ENVIRONMENTS.md](ENVIRONMENTS.md).
14. ✅ **PR 14 — Memory lifecycle:** provenienza (source/source_id/mem_type/tags),
    retrieval che registra l'uso (access_count/last_accessed) e ordina per
    score+importanza escludendo gli scaduti, retention (TTL→expires_at, prune) e
    controlli pin/importance (migrazione 0015). API `/api/v1/memories`
    (+search/prune/pin/importance) e sezione **Memory** nella pagina Knowledge.
    Vedi [MEMORY_LIFECYCLE.md](MEMORY_LIFECYCLE.md).
15. ✅ **PR 15 — Web tools:** ricerca + fetch sicuri con SSRF guard (schemi
    http/https, blocco IP privati/loopback/link-local pre- e post-DNS contro il
    DNS-rebinding, redirect ri-validati, cap dimensione/tempo), ranking BM25,
    citazioni (titolo/url/snippet/score) e allow/deny list per dominio. Off di
    default (local-first). Provider di ricerca pluggable (`none`/SearXNG). API
    `GET /api/v1/web/policy`, `POST /api/v1/web/search|fetch`. Parser puri e
    testati. Vedi [WEB_TOOLS.md](WEB_TOOLS.md).
16. ✅ **PR 16 — Evals:** suite/case/run/result (migrazione 0016), scoring puro
    (quality = substring attese, safety = substring vietate, latency), baseline,
    aggregati (pass_rate/avg_quality/avg_safety/latency p95). API
    `/api/v1/evals/*` + pagina **Evals**. Vedi [EVALS.md](EVALS.md).
17. ✅ **PR 17 — Self-healing reale:** sandbox isolato reale (`git apply` in
    check mode + comando di verifica configurato, repo mai toccato), applicazione
    governata (`apply-fix` solo dopo approvazione umana), provider GitHub reale
    dietro guardrail (off di default), API `/maintenance/sandbox|apply-fix` +
    pagina **Maintenance**. Vedi [SELF_HEALING.md](SELF_HEALING.md).
18. ✅ **PR 18 — Continuous Improvement:** proposte di miglioramento
    (migrazione 0017), esperimento baseline-vs-candidato sulle eval suite (PR 16),
    confronto metriche puro (verdetto improvement/regression/neutral, safety
    prioritaria), gate di approvazione umano e applicazione governata (imposta il
    modello di default). API `/improvements/*` + pagina **Improvements**. Vedi
    [CONTINUOUS_IMPROVEMENT.md](CONTINUOUS_IMPROVEMENT.md).
19. ✅ **PR 19 — Critical Review:** pipeline proposer/critic/verifier/judge
    (migrazione 0019), scoring puro (critic euristico, verifier su reference,
    judge = qualità+grounding), consensus adattivo (stop anticipato oltre soglia),
    API `/api/v1/reviews` + pagina **Critical Review**. Vedi
    [CRITICAL_REVIEW.md](CRITICAL_REVIEW.md).
20. ✅ **PR 20 — Unified Updater:** `./atlas update` transazionale — preflight
    (docker, compose config, spazio disco), snapshot (`.env` + dump DB), pull
    ff-only, rebuild+migrazioni (volumi preservati), health check e
    **auto-rollback** (`git reset` alla revisione precedente + rebuild) con un
    unico esito (completed / rolled-back / aborted / manual) ed exit code
    corrispondente; `--resume` dopo un tentativo interrotto. Vedi
    [UPDATER.md](UPDATER.md).
21. ✅ **PR 21 — Fleet Update:** deployment del fleet (migrazione 0020) con
    pianificazione a ondate (canary + rollout), skip nodi offline e nodi sotto la
    soglia di compatibilità, `nodes.desired_version` applicato dagli agent.
    Vedi [FLEET_DEPLOYMENT.md](FLEET_DEPLOYMENT.md).
22. ✅ **PR 22 — Safe deployment:** health gate prima della promozione (canary tutti
    HEALTHY → rollout), promozione a ondata e **rollback automatico** (ripristino
    `desired_version` precedente) su qualsiasi fallimento; API `/advance` e
    `/report`, pagina **Fleet Update**. Vedi [FLEET_DEPLOYMENT.md](FLEET_DEPLOYMENT.md).
23. **PR 23 — UI:** Nodi, Risorse, Memoria, Miglioramenti, Aggiornamenti, code e fonti.
24. **PR 24 — Fleet Compliance:** inventario, desired state, drift e dashboard.
25. **PR 25 — Auto-remediation:** rimedi, quarantena, diagnosi guidata e reintegro.
26. **PR 26 — Quality:** upgrade, failover, fault injection, recovery, CI e prova AMD.

### Estensioni utenti & privacy (aggiunte su richiesta)

27. ✅ **PR 27 — Utenti & RBAC:** ruoli `admin`/`user`, flag `ATLAS_AUTH_ENFORCE`
    (off = locale/single-operator aperto; on = login richiesto e ruoli imposti),
    dependency `require_admin`/`require_user` + `current_user_optional`, API
    `/api/v1/users` (lista/crea/patch) admin-gated con guardia sull'ultimo admin,
    pagina **Users**. Vedi [USERS_RBAC.md](USERS_RBAC.md).
28. ✅ **PR 28 — Modalità anonima & tracciata:** *anonima* (`anonymous:true`) →
    nessuna persistenza (né conversazione, né messaggi, né memoria), toggle
    **🕶 Incognito** in chat; *tracciata* → conversazioni possedute per `user_id`
    e memoria auto-catturata con `scope_id=user_id` (ognuno vede le proprie,
    l'admin tutte). Nessuna migrazione (riusa `conversations.user_id` /
    `memories.scope_id`). Vedi [PRIVACY_MODES.md](PRIVACY_MODES.md).

## Definition of Done globale

Una funzionalità o release è completata soltanto se:

- comportamento e limiti sono documentati;
- installazione pulita e upgrade sono automatici;
- configurazione e migrazioni sono idempotenti;
- test unitari, integrazione, sicurezza e failure path sono superati;
- health check verifica la funzione reale;
- metriche, log e audit sono disponibili;
- permessi e gestione secret sono applicati;
- backup/restore o rollback sono verificati;
- UI, API e accessibilità sono complete;
- nodi vecchi/incompatibili sono gestiti;
- errori producono diagnosi utile;
- nessun passaggio manuale resta dopo l'updater normale;
- criteri di accettazione sono dimostrati con evidenze.

## Requisito trasversale: updater completo a comando unico

Ogni nuova funzione deve essere integrata nel sistema di installazione e
aggiornamento. Esperienza: `sudo ./atlas update`. Al termine ATLAS deve essere
già avviato, aggiornato, migrato, configurato e verificato, con un solo risultato
terminale (completato / rollback / intervento inevitabile). Non è accettabile
terminare con una lista di comandi manuali. Flusso transazionale con lock,
preflight, backup verificato, migrazioni compatibili, canary, health check
funzionali, rollback automatico e report finale. Idempotente.

## Fuori ambito iniziale

- aggiornamento automatico schedulato senza approvazione umana;
- distribuzione simultanea dei modelli sui nodi federati;
- download da registry diversi da Ollama;
- aggiornamento automatico dell'immagine Docker `ollama/ollama`.

---

> Il testo integrale e dettagliato di ogni sezione (Ollama lifecycle, GPU AMD
> Vulkan discovery, web access, query interrompibili, risorse, coda messaggi,
> memoria/ambienti, enrollment nodi, self-healing, revisione critica, updater,
> fleet compliance, fondazioni di sicurezza) è mantenuto come riferimento
> operativo nella issue/planning e riassunto qui per release e PR. Ogni PR sopra
> apre una sezione dedicata quando viene avviata.
