import Link from "next/link";

export default function DashboardPage() {
  return (
    <div>
      <h1 className="page-title">Dashboard</h1>
      <p className="page-subtitle">
        ATLAS control plane — Sprint 1 bootstrap foundation.
      </p>
      <div className="cards">
        <div className="card">
          <h3>Getting started</h3>
          <p className="muted">
            The platform is running in its bootstrap configuration. Check the{" "}
            <Link href="/system" style={{ color: "var(--accent)" }}>
              System Status
            </Link>{" "}
            page to confirm the backend, database and Redis are healthy.
          </p>
        </div>
        <div className="card">
          <h3>What&apos;s next</h3>
          <p className="muted">
            Later milestones add local LLM inference, the task orchestrator
            (ALMA), distributed nodes, RAG/memory and the maintenance agent.
          </p>
        </div>
      </div>
    </div>
  );
}
