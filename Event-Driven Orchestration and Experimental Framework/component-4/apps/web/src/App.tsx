import { useEffect, useState } from "react";
import type { HealthCheckResponse } from "@component4/shared";

export function App() {
  const [health, setHealth] = useState<HealthCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<HealthCheckResponse>;
      })
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Component 4 — Event Intelligence Dashboard</h1>
      <p style={{ color: "#888" }}>Scaffold build — Phase 1.1</p>

      <section style={{ marginTop: "1.5rem" }}>
        <h2>API Health Check</h2>
        {error && <p style={{ color: "crimson" }}>Error: {error}</p>}
        {health && (
          <pre style={{ background: "#111", color: "#0f0", padding: "1rem", borderRadius: 8 }}>
            {JSON.stringify(health, null, 2)}
          </pre>
        )}
        {!health && !error && <p>Loading…</p>}
      </section>
    </div>
  );
}
