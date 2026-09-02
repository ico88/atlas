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

1. **PR 1 — Hardware discovery:** scanner NVIDIA/AMD/Vulkan/ROCm, permessi e API.
2. **PR 2 — Installer:** opzioni CLI, profilo `ai`, override GPU, configurazione `.env`, pull e readiness.
3. **PR 3 — Model lifecycle:** libreria condivisa, update atomico, smoke test GPU e rollback.
4. **PR 4 — Operations:** pruning protetto, Makefile, logging e documentazione.
5. **PR 5 — Node Setup UI:** installazione dipendenze, ZeroTier, Network ID e recovery.
6. **PR 6 — Node enrollment:** inviti UI, mTLS, approvazione, rotazione e revoca.
7. **PR 7 — ZeroTier integration:** stato, policy, API controller opzionale e audit.
8. **PR 8 — Resilient scheduler:** lease, checkpoint, failover, fencing e task tardivi.
9. **PR 9 — Control plane HA:** replica, leader election e disaster recovery.
10. **PR 10 — Query lifecycle:** persistenza, background, cancellazione e recupero.
11. **PR 11 — Conversation queue:** invio immediato, accodamento, merge e parallelismo.
12. **PR 12 — Resource telemetry:** metriche nodi, performance Ollama e storage storico.
13. **PR 13 — Environments:** modello dati, manifest, isolamento, snapshot e restore.
14. **PR 14 — Memory lifecycle:** acquisizione, retrieval, provenienza e retention.
15. **PR 15 — Web tools:** ricerca, fetch sicuro, ranking, citazioni e policy.
16. **PR 16 — Evals:** dataset, baseline e metriche di qualità, sicurezza e prestazioni.
17. **PR 17 — Self-healing reale:** sandbox, GitHub, patch, test e PR governate.
18. **PR 18 — Continuous Improvement:** proposte, esperimenti, confronto e approvazioni.
19. **PR 19 — Critical Review:** proposer, critic, verifier, judge e consensus adattivo.
20. **PR 20 — Unified Updater:** comando unico, preflight, snapshot, migrazioni e ripresa.
21. **PR 21 — Fleet Update:** rolling update, nodi canary, compatibilità e nodi offline.
22. **PR 22 — Safe deployment:** health gate, promozione e rollback.
23. **PR 23 — UI:** Nodi, Risorse, Memoria, Miglioramenti, Aggiornamenti, code e fonti.
24. **PR 24 — Fleet Compliance:** inventario, desired state, drift e dashboard.
25. **PR 25 — Auto-remediation:** rimedi, quarantena, diagnosi guidata e reintegro.
26. **PR 26 — Quality:** upgrade, failover, fault injection, recovery, CI e prova AMD.

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
