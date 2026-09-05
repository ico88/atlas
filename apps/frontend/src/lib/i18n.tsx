"use client";

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export type Lang = "en" | "it";

type Dict = Record<string, string>;

// Translations. English is the fallback; add keys to both maps as UI grows.
const EN: Dict = {
  "nav.chat": "Chat",
  "nav.dashboard": "Dashboard",
  "nav.queries": "Queries",
  "nav.queue": "Queue",
  "nav.tasks": "Tasks",
  "nav.system": "System Status",
  "nav.nodes": "Nodes",
  "nav.fleet": "Fleet Update",
  "nav.compliance": "Fleet Health",
  "nav.resources": "Resources",
  "nav.models": "Models",
  "nav.knowledge": "Knowledge",
  "nav.environments": "Environments",
  "nav.maintenance": "Maintenance",
  "nav.evals": "Evals",
  "nav.improvements": "Improvements",
  "nav.reviews": "Critical Review",
  "nav.escalation": "Escalation",
  "nav.users": "Users",
  "nav.settings": "Settings",
  "nav.section.work": "Workspace",
  "nav.section.fleet": "Fleet",
  "nav.section.govern": "Governance",
  "nav.section.admin": "Admin",
  "sidebar.tagline": "Adaptive Task & LLM Array System",
  "sidebar.footer": "Local-first · Human-governed",
  "sidebar.language": "Language",
  "auth.login": "Log in",
  "auth.logout": "Log out",
  "auth.email": "Email",
  "auth.password": "Password",
  "auth.title": "Sign in to ATLAS",
  "auth.signedInAs": "Signed in as",
  "auth.guest": "Not signed in",

  "chat.title": "Chat",
  "chat.subtitle":
    "Local-first chat. Type a message, or a command like /web, /remember, /recall, /search — everything from here.",
  "chat.newChat": "+ New chat",
  "chat.untitled": "Untitled",
  "chat.empty": "Start the conversation below, or try a command:",
  "chat.placeholder": "Type a message or /command…",
  "chat.placeholderWeb": "Ask — I'll search the web…",
  "chat.send": "Send",
  "chat.stop": "Stop",
  "chat.web": "Web",
  "chat.auto": "Auto",
  "chat.thinking": "Thinking…",
  "chat.searching": "Searching the web…",
  "chat.generating": "generating…",
  "chat.modelLoad": "first reply loads the model, hang tight…",
  "chat.sources": "Sources",
  "chat.resilientHint":
    "Runs keep going even if you close this tab — the reply is saved to the conversation.",
  "chat.archive": "Archive",
  "chat.unarchive": "Unarchive",
  "chat.delete": "Delete",
  "chat.showArchived": "Archived",
  "chat.showActive": "Active",
  "chat.confirmDelete": "Delete this chat and all its content? This cannot be undone.",
  "chat.noArchived": "No archived chats.",
  "chat.working": "Working on your request…",
  "chat.resuming": "This reply is still being generated — it will keep going even if you leave.",
  "chat.interrupted": "⚠ interrupted — send the message again",
  "chat.anon": "Incognito",
  "chat.anonHint": "Incognito: this turn is not saved (no history, no memory).",

  "dash.subtitle": "Everything at a glance — health, fleet, work and governance.",
  "dash.health": "Health",
  "dash.healthy": "Healthy",
  "dash.degraded": "Degraded",
  "dash.nodesOnline": "Nodes online",
  "dash.compliance": "Fleet compliance",
  "dash.tasksRunning": "Tasks running",
  "dash.tasksQueued": "Tasks queued",
  "dash.approvals": "Pending approvals",
  "dash.system": "System",
  "dash.model": "Default model",
  "dash.quickLinks": "Quick links",

  "common.error": "Error",
  "common.loading": "Loading…",
  "common.delete": "Delete",
  "common.save": "Save",

  "nav.runtimes": "AI Runtimes",
  "runtimes.subtitle":
    "Runtimes, model deployments and aliases. ATLAS routes each request to the best model × runtime × node — Ollama, llama.cpp, vLLM, cloud.",
  "runtimes.runtimes": "Runtimes",
  "runtimes.deployments": "Model deployments",
  "runtimes.deployments.help": "A model made available through a runtime (a model can be deployed on many).",
  "runtimes.aliases": "Model aliases",
  "runtimes.aliases.help": "Stable names ALMA uses (atlas.general) mapped to an ordered list of model keys.",
  "runtimes.name": "name",
  "runtimes.type": "Type",
  "runtimes.add": "Add",
  "runtimes.none": "Nothing yet.",
};

const IT: Dict = {
  "nav.chat": "Chat",
  "nav.dashboard": "Cruscotto",
  "nav.queries": "Interrogazioni",
  "nav.queue": "Coda",
  "nav.tasks": "Attività",
  "nav.system": "Stato sistema",
  "nav.nodes": "Nodi",
  "nav.fleet": "Aggiornamento fleet",
  "nav.compliance": "Salute fleet",
  "nav.resources": "Risorse",
  "nav.models": "Modelli",
  "nav.knowledge": "Conoscenza",
  "nav.environments": "Ambienti",
  "nav.maintenance": "Manutenzione",
  "nav.evals": "Valutazioni",
  "nav.improvements": "Miglioramenti",
  "nav.reviews": "Revisione critica",
  "nav.escalation": "Escalation",
  "nav.users": "Utenti",
  "nav.settings": "Impostazioni",
  "nav.section.work": "Area di lavoro",
  "nav.section.fleet": "Fleet",
  "nav.section.govern": "Governance",
  "nav.section.admin": "Amministrazione",
  "sidebar.tagline": "Sistema adattivo di attività e modelli LLM",
  "sidebar.footer": "Locale · Governato dall'uomo",
  "sidebar.language": "Lingua",
  "auth.login": "Accedi",
  "auth.logout": "Esci",
  "auth.email": "Email",
  "auth.password": "Password",
  "auth.title": "Accedi ad ATLAS",
  "auth.signedInAs": "Accesso come",
  "auth.guest": "Non autenticato",

  "chat.title": "Chat",
  "chat.subtitle":
    "Chat locale. Scrivi un messaggio o un comando come /web, /remember, /recall, /search — tutto da qui.",
  "chat.newChat": "+ Nuova chat",
  "chat.untitled": "Senza titolo",
  "chat.empty": "Inizia la conversazione qui sotto, o prova un comando:",
  "chat.placeholder": "Scrivi un messaggio o /comando…",
  "chat.placeholderWeb": "Chiedi — cerco sul web…",
  "chat.send": "Invia",
  "chat.stop": "Ferma",
  "chat.web": "Web",
  "chat.auto": "Auto",
  "chat.thinking": "Sto pensando…",
  "chat.searching": "Sto cercando sul web…",
  "chat.generating": "sto generando…",
  "chat.modelLoad": "la prima risposta carica il modello, un attimo…",
  "chat.sources": "Fonti",
  "chat.resilientHint":
    "L'elaborazione continua anche se chiudi questa scheda — la risposta viene salvata nella conversazione.",
  "chat.archive": "Archivia",
  "chat.unarchive": "Ripristina",
  "chat.delete": "Elimina",
  "chat.showArchived": "Archiviate",
  "chat.showActive": "Attive",
  "chat.confirmDelete": "Eliminare questa chat e tutto il contenuto? Operazione irreversibile.",
  "chat.noArchived": "Nessuna chat archiviata.",
  "chat.working": "Sto elaborando la tua richiesta…",
  "chat.resuming": "Questa risposta è ancora in generazione — continua anche se esci.",
  "chat.interrupted": "⚠ interrotta — reinvia il messaggio",
  "chat.anon": "Incognito",
  "chat.anonHint": "Incognito: questo turno non viene salvato (né cronologia né memoria).",

  "dash.subtitle": "Tutto in un colpo d'occhio — salute, fleet, lavoro e governance.",
  "dash.health": "Salute",
  "dash.healthy": "In salute",
  "dash.degraded": "Degradato",
  "dash.nodesOnline": "Nodi online",
  "dash.compliance": "Conformità fleet",
  "dash.tasksRunning": "Attività in corso",
  "dash.tasksQueued": "Attività in coda",
  "dash.approvals": "Approvazioni in attesa",
  "dash.system": "Sistema",
  "dash.model": "Modello predefinito",
  "dash.quickLinks": "Collegamenti rapidi",

  "common.error": "Errore",
  "common.loading": "Caricamento…",
  "common.delete": "Elimina",
  "common.save": "Salva",

  "nav.runtimes": "Runtime AI",
  "runtimes.subtitle":
    "Runtime, deployment dei modelli e alias. ATLAS instrada ogni richiesta al miglior modello × runtime × nodo — Ollama, llama.cpp, vLLM, cloud.",
  "runtimes.runtimes": "Runtime",
  "runtimes.deployments": "Deployment dei modelli",
  "runtimes.deployments.help": "Un modello reso disponibile tramite un runtime (un modello può stare su più runtime).",
  "runtimes.aliases": "Alias dei modelli",
  "runtimes.aliases.help": "Nomi stabili usati da ALMA (atlas.general) mappati a un elenco ordinato di model key.",
  "runtimes.name": "nome",
  "runtimes.type": "Tipo",
  "runtimes.add": "Aggiungi",
  "runtimes.none": "Ancora niente.",
};

const DICT: Record<Lang, Dict> = { en: EN, it: IT };

type I18n = { lang: Lang; setLang: (l: Lang) => void; t: (key: string) => string };

const I18nContext = createContext<I18n>({
  lang: "en",
  setLang: () => {},
  t: (k) => EN[k] ?? k,
});

const STORAGE_KEY = "atlas.lang";

export function I18nProvider({ children }: { children: ReactNode }) {
  // Start "en" so server and first client render match (no hydration mismatch);
  // the real preference is applied right after mount.
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "en" || saved === "it") {
        setLangState(saved);
        return;
      }
    } catch {
      /* storage unavailable */
    }
    if (typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("it")) {
      setLangState("it");
    }
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
      document.documentElement.lang = l;
    } catch {
      /* storage unavailable */
    }
  }, []);

  const t = useCallback(
    (key: string) => DICT[lang][key] ?? EN[key] ?? key,
    [lang],
  );

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>
  );
}

export const useI18n = (): I18n => useContext(I18nContext);
