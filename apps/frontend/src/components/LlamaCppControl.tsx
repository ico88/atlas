"use client";

import { useState } from "react";

const SAMPLE_MODELS = [
  "deepseek-7b-q4.gguf",
  "llama2-13b-q5.gguf",
  "mistral-7b-q4.gguf",
  "neural-chat-7b-q4.gguf",
];

export default function LlamaCppControl() {
  const [running, setRunning] = useState(true);
  const [loadedModel, setLoadedModel] = useState("deepseek-7b-q4.gguf");
  const [context, setContext] = useState(2048);
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(0.9);
  const [selectedModel, setSelectedModel] = useState("deepseek-7b-q4.gguf");
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setRunning(true);
    // TODO: call POST /api/v1/llama-cpp/start
  };

  const handleStop = async () => {
    setRunning(false);
    // TODO: call POST /api/v1/llama-cpp/stop
  };

  const handleLoadModel = async () => {
    setLoading(true);
    // TODO: call POST /api/v1/llama-cpp/load with { model: selectedModel }
    setTimeout(() => {
      setLoadedModel(selectedModel);
      setLoading(false);
    }, 1000);
  };

  const handleParameterChange = async (param: string, value: number) => {
    // TODO: call PATCH /api/v1/llama-cpp/inference-params with { [param]: value }
  };

  return (
    <div className="card" style={{ marginBottom: 20, borderColor: "var(--highlight-soft)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 14, textTransform: "uppercase", letterSpacing: "1px", color: "var(--muted)" }}>
          ⚙ llama.cpp Engine Control
        </h3>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 12,
            fontWeight: 600,
            padding: "4px 10px",
            borderRadius: 6,
            background: running ? "rgba(31, 157, 85, 0.16)" : "rgba(211, 59, 48, 0.16)",
            color: running ? "var(--ok)" : "var(--bad)",
          }}
        >
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "currentColor" }} />
          {running ? "Running" : "Stopped"}
        </span>
      </div>

      {/* Model section */}
      <div style={{ marginBottom: 16, padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
        <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--muted)", marginBottom: 8 }}>
          Current Model
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <span className="metric" style={{ fontSize: 13, fontWeight: 600 }}>
            {loadedModel}
          </span>
          <span className="pill" style={{ fontSize: 11 }}>~3.5 GB</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--panel)", color: "var(--text)", fontSize: 13 }}
          >
            {SAMPLE_MODELS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <button
            className="btn"
            disabled={selectedModel === loadedModel || loading || !running}
            onClick={handleLoadModel}
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            {loading ? "Loading..." : "Load"}
          </button>
        </div>
      </div>

      {/* Inference parameters */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--muted)", marginBottom: 12 }}>
          Inference Parameters
        </div>

        {/* Context */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <label style={{ fontSize: 12, color: "var(--text)" }}>Context (tokens)</label>
            <span className="highlight" style={{ fontSize: 12, fontWeight: 600 }}>
              {context}
            </span>
          </div>
          <input
            type="range"
            min="512"
            max="4096"
            step="256"
            value={context}
            onChange={(e) => {
              const val = parseInt(e.target.value);
              setContext(val);
              handleParameterChange("context", val);
            }}
            style={{
              width: "100%",
              accentColor: "var(--highlight)",
              cursor: "pointer",
            }}
          />
        </div>

        {/* Temperature */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <label style={{ fontSize: 12, color: "var(--text)" }}>Temperature</label>
            <span className="highlight" style={{ fontSize: 12, fontWeight: 600 }}>
              {temperature.toFixed(2)}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="2"
            step="0.05"
            value={temperature}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              setTemperature(val);
              handleParameterChange("temperature", val);
            }}
            style={{
              width: "100%",
              accentColor: "var(--highlight)",
              cursor: "pointer",
            }}
          />
        </div>

        {/* Top-P */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <label style={{ fontSize: 12, color: "var(--text)" }}>Top-P (nucleus)</label>
            <span className="highlight" style={{ fontSize: 12, fontWeight: 600 }}>
              {topP.toFixed(2)}
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.02"
            value={topP}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              setTopP(val);
              handleParameterChange("top_p", val);
            }}
            style={{
              width: "100%",
              accentColor: "var(--highlight)",
              cursor: "pointer",
            }}
          />
        </div>
      </div>

      {/* Control buttons */}
      <div style={{ display: "flex", gap: 8, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
        <button
          className={`btn ${running ? "secondary" : ""}`}
          onClick={handleStart}
          disabled={running}
          style={{ flex: 1 }}
        >
          ▶ Start
        </button>
        <button
          className={`btn ${!running ? "secondary" : ""}`}
          onClick={handleStop}
          disabled={!running}
          style={{ flex: 1 }}
        >
          ⏹ Stop
        </button>
      </div>

      {/* Stats footer */}
      {running && (
        <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--panel-2)", borderRadius: 8, fontSize: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <div style={{ color: "var(--muted)", fontSize: 11 }}>Memory</div>
            <div className="metric" style={{ fontSize: 12, fontWeight: 600 }}>2.8 GB / 3.5 GB</div>
          </div>
          <div>
            <div style={{ color: "var(--muted)", fontSize: 11 }}>Throughput</div>
            <div className="metric" style={{ fontSize: 12, fontWeight: 600 }}>126.4 t/s</div>
          </div>
        </div>
      )}
    </div>
  );
}
