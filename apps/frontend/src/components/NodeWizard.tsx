"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Enrollment,
  EnrollmentWithToken,
  SetupNode,
  ZeroTierStatus,
  approveEnrollment,
  attachNodeModel,
  authorizeZeroTier,
  createEnrollment,
  fetchEnrollments,
  fetchSetupNodes,
  fetchTaskProgress,
  fetchZeroTier,
  setupNodePull,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function Step({ n, title, done, children }: {
  n: number;
  title: string;
  done?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="wizard-step">
      <div className="wizard-step-head">
        <span className={`wizard-num${done ? " done" : ""}`}>{done ? "✓" : n}</span>
        <strong>{title}</strong>
      </div>
      <div className="wizard-step-body">{children}</div>
    </div>
  );
}

export default function NodeWizard() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [nodeId, setNodeId] = useState("");
  const [label, setLabel] = useState("");
  const [minted, setMinted] = useState<EnrollmentWithToken | null>(null);
  const [zt, setZt] = useState<ZeroTierStatus | null>(null);
  const [nodes, setNodes] = useState<SetupNode[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [model, setModel] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pull, setPull] = useState<{ percent: number; status: string } | null>(null);
  const pullPoll = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      setZt(await fetchZeroTier());
    } catch {
      /* controller off */
    }
    try {
      setNodes((await fetchSetupNodes()).nodes);
    } catch {
      /* ignore */
    }
    try {
      setEnrollments((await fetchEnrollments()).items);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [open, refresh]);

  useEffect(() => () => {
    if (pullPoll.current) clearInterval(pullPoll.current);
  }, []);

  const enrollment = enrollments.find((e) => e.node_id === nodeId) || null;
  const node = nodes.find((n) => n.node_id === nodeId) || null;
  const online = !!node?.online;

  useEffect(() => {
    if (!node) return;
    if (!endpoint && node.ollama_url) setEndpoint(node.ollama_url);
    if (!model && node.recommendation) setModel(node.recommendation.primary.model);
  }, [node, endpoint, model]);

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg(ok);
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  };

  // One-click pull with live progress: start the task, then poll it.
  const startPull = async () => {
    if (!model.trim()) return;
    setErr(null);
    setMsg(null);
    setPull({ percent: 0, status: "queued" });
    try {
      const res = await setupNodePull(nodeId, model.trim());
      const taskId = res.task_id;
      if (pullPoll.current) clearInterval(pullPoll.current);
      pullPoll.current = setInterval(async () => {
        try {
          const tp = await fetchTaskProgress(taskId);
          const p = tp.checkpoint?.progress;
          if (tp.status === "COMPLETED") {
            if (pullPoll.current) clearInterval(pullPoll.current);
            setPull({ percent: 100, status: "done" });
            setMsg(t("wizard.pullDone"));
            await refresh();
          } else if (tp.status === "FAILED") {
            if (pullPoll.current) clearInterval(pullPoll.current);
            setPull(null);
            setErr(tp.error || "pull failed");
          } else if (p) {
            setPull({ percent: p.percent, status: p.status || "pulling" });
          }
        } catch {
          /* transient */
        }
      }, 1500);
    } catch (e) {
      setPull(null);
      setErr(e instanceof Error ? e.message : "pull failed");
    }
  };

  const invite = () =>
    run(async () => {
      const res = await createEnrollment({ node_id: nodeId.trim(), label: label.trim() || undefined });
      setMinted(res);
    });

  const ztNetwork = zt?.network_id || "";
  const composeEnv = [
    `ATLAS_CONTROL_PLANE_URL=http://<manager-ip>:80`,
    `ATLAS_NODE_ID=${nodeId || "<node-id>"}`,
    minted ? `ATLAS_NODE_TOKEN=${minted.token}` : `ATLAS_NODE_TOKEN=<token-dal-passo-1>`,
    `ATLAS_NETWORK_PROVIDER=zerotier`,
    ztNetwork ? `ATLAS_ZEROTIER_NETWORK_ID=${ztNetwork}` : `ATLAS_ZEROTIER_NETWORK_ID=<network-id>`,
    `ATLAS_NODE_OLLAMA_ADVERTISE_URL=http://<ip-overlay-del-nodo>:11434`,
  ].join("\n");

  if (!open) {
    return (
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="status-row">
          <strong>{t("wizard.title")}</strong>
          <button className="btn" onClick={() => setOpen(true)}>
            {t("wizard.open")}
          </button>
        </div>
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>{t("wizard.subtitle")}</p>
      </div>
    );
  }

  return (
    <div className="card wizard" style={{ marginBottom: 16 }}>
      <div className="status-row">
        <strong>{t("wizard.title")}</strong>
        <button className="btn secondary" onClick={() => setOpen(false)}>
          {t("wizard.close")}
        </button>
      </div>
      {err && <p className="error">{err}</p>}
      {msg && <p className="muted">✅ {msg}</p>}

      {/* Step 1 — identity + invite */}
      <Step n={1} title={t("wizard.s1")} done={!!minted || !!enrollment}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={nodeId}
            placeholder="node id (es. worker-2)"
            onChange={(e) => setNodeId(e.target.value)}
            style={{ flex: "1 1 160px" }}
          />
          <input
            value={label}
            placeholder={t("wizard.labelOpt")}
            onChange={(e) => setLabel(e.target.value)}
            style={{ flex: "1 1 140px" }}
          />
          <button className="btn" disabled={!nodeId.trim() || busy} onClick={invite}>
            {t("wizard.invite")}
          </button>
        </div>
        {minted && (
          <div className="card" style={{ marginTop: 10 }}>
            <p className="muted" style={{ fontSize: 12 }}>{t("wizard.tokenOnce")}</p>
            <pre style={{ overflow: "auto" }}>{minted.token}</pre>
          </div>
        )}
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>{t("wizard.installHint")}</p>
        <pre style={{ overflow: "auto" }}>
          {`./infrastructure/scripts/install.sh --role node\ndocker compose -f docker-compose.node.yml up -d`}
        </pre>
      </Step>

      {/* Step 2 — network / ZeroTier */}
      <Step n={2} title={t("wizard.s2")}>
        <p className="muted" style={{ fontSize: 13 }}>
          {ztNetwork ? t("wizard.ztHave") : t("wizard.ztNone")}
          {ztNetwork && <> <code>{ztNetwork}</code></>}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>{t("wizard.envHint")}</p>
        <pre style={{ overflow: "auto" }}>{composeEnv}</pre>
        {zt?.controller_enabled && zt.members.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <p className="muted" style={{ fontSize: 12 }}>{t("wizard.ztAuthorize")}</p>
            {zt.members.map((m) => (
              <div className="status-row" key={m.id}>
                <span>{m.name || m.id} — {m.ip_assignments.join(", ") || "—"}</span>
                <button
                  className={m.authorized ? "btn secondary" : "btn"}
                  disabled={busy}
                  onClick={() => run(() => authorizeZeroTier(m.id, !m.authorized))}
                >
                  {m.authorized ? t("wizard.deauth") : t("wizard.auth")}
                </button>
              </div>
            ))}
          </div>
        )}
      </Step>

      {/* Step 3 — approve + wait online */}
      <Step n={3} title={t("wizard.s3")} done={online}>
        {!enrollment && <p className="muted">{t("wizard.s3wait")}</p>}
        {enrollment && (
          <div className="status-row">
            <span>
              {enrollment.node_id} —{" "}
              <span className={`queue-badge ${enrollment.status === "APPROVED" ? "active" : "idle"}`}>
                {enrollment.status}
              </span>
            </span>
            {enrollment.status !== "APPROVED" && (
              <button className="btn" disabled={busy} onClick={() => run(() => approveEnrollment(enrollment.id), t("wizard.approved"))}>
                {t("wizard.approve")}
              </button>
            )}
          </div>
        )}
        <p className="muted" style={{ fontSize: 13, marginTop: 6 }}>
          {online ? `✅ ${t("wizard.nodeOnline")}` : `⏳ ${t("wizard.nodeOffline")}`}
        </p>
      </Step>

      {/* Step 4 — model */}
      <Step n={4} title={t("wizard.s4")} done={!!node && node.attached_models.length > 0}>
        {!online && <p className="muted">{t("wizard.s4wait")}</p>}
        {online && (
          <>
            {node?.recommendation && (
              <p className="muted" style={{ fontSize: 12 }}>
                {t("setup.recommended")}: <strong>{node.recommendation.primary.label}</strong>
              </p>
            )}
            <div style={{ display: "grid", gap: 6 }}>
              <input value={model} placeholder="modello (es. qwen2.5:3b)" onChange={(e) => setModel(e.target.value)} />
              <button
                className="btn secondary"
                disabled={!model.trim() || (pull !== null && pull.percent < 100)}
                onClick={startPull}
              >
                {pull !== null && pull.percent < 100
                  ? `${t("wizard.pulling")} ${pull.percent}%`
                  : t("wizard.pull")}
              </button>
              {pull !== null && (
                <div className="progress-bar" aria-label="download">
                  <div className="progress-fill" style={{ width: `${pull.percent}%` }} />
                </div>
              )}
              <input value={endpoint} placeholder="endpoint (es. http://10.147.x.x:11434)" onChange={(e) => setEndpoint(e.target.value)} />
              <button className="btn" disabled={busy || !model.trim() || !endpoint.trim()} onClick={() => run(() => attachNodeModel(nodeId, model.trim(), endpoint.trim()), t("wizard.attached"))}>
                {t("wizard.attach")}
              </button>
            </div>
            {node && node.attached_models.length > 0 && (
              <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                {t("setup.node.models")}: {node.attached_models.join(", ")}
              </p>
            )}
          </>
        )}
      </Step>
    </div>
  );
}
