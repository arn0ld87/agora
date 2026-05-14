/* Agora Design System — App Screens A: LLM Routing · Integrations · Monitoring */

const DSA = {};

// ─── 1) LLM Routing ─────────────────────────────────────────
DSA.LLMRouting = () => (
  <DSAppShell active="settings" openGroup="settings" subActive="llm-routing"
    crumbs={["Settings", "LLM Routing"]}>
    <DSPageHeader title="LLM Routing" subtitle="Provider, Modellwahl und Stage-Routing pro Run konfigurieren."/>

    <div style={{ display: "grid", gridTemplateColumns: "1.05fr 1fr", gap: 20 }}>
      {/* Global Default */}
      <DSCard title="Global Default">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          <DSField label="Provider"><DSSelect value="openai"/></DSField>
          <DSField label="Model"><DSSelect value="gpt-5.5"/></DSField>
          <DSField label="Reasoning effort"><DSSelect value="medium"/></DSField>
        </div>
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 6 }}>Provider options (JSON)</div>
          <pre style={{
            margin: 0, padding: 12, background: "#fff",
            border: "1px solid var(--hairline)", borderRadius: 8,
            fontFamily: "var(--font-mono)", fontSize: 12.5, lineHeight: 1.6,
            color: "var(--text-primary)",
          }}>{`{
  "num_ctx": 32768,
  "temperature": 0.2
}`}</pre>
        </div>
      </DSCard>

      {/* Aktive Snapshots */}
      <DSCard title="Aktive Snapshots">
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <span className="pill pill--blue">Configured routing version:&nbsp;<b>8</b></span>
          <span className="pill pill--purple">Active snapshot version:&nbsp;<b>7</b></span>
        </div>
        <div style={{
          padding: "10px 12px", borderRadius: 10,
          background: "var(--accent-tint-bg)", color: "var(--accent-tint-text)",
          fontSize: 13, display: "flex", gap: 8, marginBottom: 14, alignItems: "flex-start",
        }}>
          <Icon name="bolt" size={14}/>
          <span style={{ color: "var(--text-secondary)" }}>Laufende Stages sind für die Ausführung gesperrt. Änderungen gelten für noch nicht gestartete Stages.</span>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Stage</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["document_ingest", "Completed", "green"],
              ["ontology_generation", "Completed", "green"],
              ["graph_build", "Completed", "green"],
              ["persona_generation", "Completed", "green"],
              ["simulation_rounds", "Running", "orange"],
              ["report_generation", "Pending", "gray"],
            ].map(([stage, status, c]) => (
              <tr key={stage} style={{ borderTop: "1px solid var(--separator)" }}>
                <td style={{ padding: "10px 8px", fontFamily: "var(--font-mono)", fontSize: 13 }}>{stage}</td>
                <td style={{ padding: "10px 8px" }}>
                  <span className={`pill pill--${c}`}><span className="dot"/>{status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DSCard>
    </div>

    {/* Stage Overrides + Custom model */}
    <div style={{ display: "grid", gridTemplateColumns: "1.05fr 1fr", gap: 20, marginTop: 20 }}>
      <DSCard title="Stage Overrides">
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Stage</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Provider</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Model</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Effort</th>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["document_ingest","ollama_local","qwen3-coder-next:cloud","medium","Draft","purple"],
              ["ontology_generation","google","gemini-3-flash","medium","Draft","purple"],
              ["graph_build","openai","gpt-5.5-mini","low","Pending","gray"],
              ["persona_generation","google","gemini-3-pro","high","Draft","purple"],
              ["simulation_rounds","openai","gpt-5.5","high","Pending","gray"],
              ["report_generation","openai","gpt-5.5","medium","Draft","purple"],
              ["evaluation","openai_compatible","deepseek-v4-flash:cloud","low","Pending","gray"],
            ].map((r) => (
              <tr key={r[0]} style={{ borderTop: "1px solid var(--separator)" }}>
                <td style={{ padding: "10px 8px", fontFamily: "var(--font-mono)", fontSize: 13 }}>{r[0]}</td>
                <td style={{ padding: "10px 8px", color: "var(--text-secondary)" }}>{r[1]}</td>
                <td style={{ padding: "10px 8px", fontFamily: "var(--font-mono)" }}>{r[2]}</td>
                <td style={{ padding: "10px 8px", color: "var(--text-secondary)" }}>{r[3]}</td>
                <td style={{ padding: "10px 8px" }}><span className={`pill pill--${r[5]}`}><span className="dot"/>{r[4]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 18 }}>
          <button className="btn btn--secondary"><Icon name="plus" size={12}/>Stage Override</button>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn--secondary">Zurücksetzen</button>
            <button className="btn btn--primary">Speichern</button>
          </div>
        </div>
      </DSCard>

      <DSCard title="Custom Model hinzufügen" subtitle="Für Modelle, die nicht automatisch in der API-Liste auftauchen.">
        <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 12, alignItems: "center" }}>
          {[
            ["Provider", "ollama_cloud"],
            ["Model ID", "kimi-k2.6:cloud"],
            ["Base URL", "https://api.ollama.com/v1"],
            ["Capabilities", "chat, tools, json, reasoning"],
          ].map(([k, v]) => (
            <React.Fragment key={k}>
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{k}</span>
              <DSInput value={v} mono={k!=="Capabilities"}/>
            </React.Fragment>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <button className="btn btn--primary">Speichern</button>
          <button className="btn btn--secondary">Abbrechen</button>
        </div>
      </DSCard>
    </div>
  </DSAppShell>
);

// ─── 2) Integrations ────────────────────────────────────────
DSA.Integrations = () => {
  const Provider = ({ name, sub, status, statusColor }) => (
    <DSCard pad={18}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.005em" }}>{name}</span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{sub}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16 }}>
        <span className={`pill pill--${statusColor}`}><span className="dot"/>{status}</span>
        <button className="btn btn--secondary btn--sm">Edit</button>
      </div>
    </DSCard>
  );

  return (
    <DSAppShell active="settings" openGroup="settings" subActive="integrations"
      crumbs={["Settings", "Integrations"]}>
      <DSPageHeader title="Integrations" subtitle="Provider, OAuth-Logins und automatische Modellsynchronisierung."/>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        <Provider name="OpenAI"            sub="API Key · Models live"    status="Connected"     statusColor="green"/>
        <Provider name="Google Gemini"     sub="API Key · Safety Settings" status="Connected"    statusColor="green"/>
        <Provider name="Ollama Cloud"      sub="Ollama API · Cloud Models" status="Connected"    statusColor="green"/>
        <Provider name="OpenAI Compatible" sub="Base URL + Key"            status="Configured"   statusColor="blue"/>
        <Provider name="GitHub Copilot"    sub="OAuth Login · Code Assist" status="Not connected" statusColor="gray"/>
        <Provider name="Local Ollama"      sub="http://127.0.0.1:11434"    status="Offline"      statusColor="red"/>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 20, marginTop: 22 }}>
        <DSCard title="Model Sync" subtitle="Aktuelle Modelle per API holen und nach Stage mappen">
          <div style={{ fontSize: 12.5, color: "var(--text-tertiary)", marginBottom: 12 }}>Letzte Synchronisierung: 2026-05-11 06:31</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>Model</th>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>Provider</th>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>Tag</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["gpt-5.5","OpenAI","Live","green"],
                ["gemini-3-pro","Google","Live","green"],
                ["qwen3-coder-next:cloud","Ollama Cloud","Synced","blue"],
                ["deepseek-v4-flash:cloud","Ollama Cloud","Draft","purple"],
              ].map((r) => (
                <tr key={r[0]} style={{ borderTop: "1px solid var(--separator)" }}>
                  <td style={{ padding: "10px 8px", fontFamily: "var(--font-mono)" }}>{r[0]}</td>
                  <td style={{ padding: "10px 8px", color: "var(--text-secondary)" }}>{r[1]}</td>
                  <td style={{ padding: "10px 8px" }}><span className={`pill pill--${r[3]}`}><span className="dot"/>{r[2]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </DSCard>

        <DSCard title="OAuth Flow" subtitle="Copilot / Antigravity / GitHub Login sauber trennen">
          {[
            ["Redirect URI registrieren","/auth/github/callback"],
            ["Scopes minimal halten","read:user, copilot/models"],
            ["Token verschlüsseln","KMS oder libsodium sealed box"],
            ["Modelle pro User freigeben","RBAC + Audit Log"],
          ].map(([t, s], i) => (
            <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderTop: i ? "1px solid var(--separator)" : "0" }}>
              <span style={{
                width: 26, height: 26, borderRadius: "50%",
                background: "var(--accent-tint-bg)", color: "var(--accent)",
                fontSize: 12, fontWeight: 700, display: "flex",
                alignItems: "center", justifyContent: "center", flex: "none",
              }}>{i + 1}</span>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{t}</span>
                <span style={{ fontSize: 12.5, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{s}</span>
              </div>
            </div>
          ))}
        </DSCard>
      </div>
    </DSAppShell>
  );
};

// ─── 3) Monitoring ──────────────────────────────────────────
DSA.Monitoring = () => {
  const KPI = ({ label, value, sub }) => (
    <DSCard pad={20}>
      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.018em", marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: 12.5, color: "var(--text-tertiary)", marginTop: 6 }}>{sub}</div>
    </DSCard>
  );

  const Tab = ({ label, active }) => (
    <span style={{
      padding: "7px 14px", borderRadius: 8,
      fontSize: 14, fontWeight: active ? 600 : 500,
      color: active ? "var(--accent)" : "var(--text-secondary)",
      border: active ? "1px solid var(--accent-tint-bg-strong)" : "1px solid transparent",
      background: active ? "var(--accent-tint-bg)" : "transparent",
    }}>{label}</span>
  );

  return (
    <DSAppShell active="monitoring" crumbs={["Monitoring"]}>
      <DSPageHeader title="Monitoring" subtitle="Runtime, Kosten, Modellqualität und Audit-Signale."
        right={
          <div style={{ display: "flex", gap: 6 }}>
            <Tab label="Runtime" active/>
            <Tab label="Kosten"/>
            <Tab label="Modelle"/>
            <Tab label="Alerts"/>
            <Tab label="Audit"/>
          </div>
        }/>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        <KPI label="p95 Latenz" value="18.4s" sub="LLM calls"/>
        <KPI label="Fehlerquote" value="1.7%" sub="letzte 24h"/>
        <KPI label="Queue" value="6 Jobs" sub="2 high prio"/>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
        <DSCard title="LLM Latenz" subtitle="p50 / p95 über Zeit" pad={18}>
          <svg viewBox="0 0 400 140" style={{ width: "100%", height: 160 }}>
            <line x1="0" y1="120" x2="400" y2="120" stroke="var(--hairline)" strokeWidth="1"/>
            <polyline points="20,90 70,80 120,84 170,68 220,60 270,52 320,58 370,30"
              fill="none" stroke="var(--accent)" strokeWidth="2.2"/>
            {[[20,90],[70,80],[120,84],[170,68],[220,60],[270,52],[320,58],[370,30]].map(([x,y]) => (
              <circle key={x} cx={x} cy={y} r="3.5" fill="var(--accent)"/>
            ))}
          </svg>
        </DSCard>

        <DSCard title="Tokenverbrauch" subtitle="Nach Provider" pad={18}>
          <svg viewBox="0 0 400 140" style={{ width: "100%", height: 160 }}>
            <line x1="0" y1="120" x2="400" y2="120" stroke="var(--hairline)" strokeWidth="1"/>
            {[60, 80, 50, 110, 95, 120, 100, 115].map((h, i) => (
              <rect key={i} x={25 + i*45} y={120 - h} width="30" height={h}
                fill="var(--accent-tint-bg-strong)" rx="3"/>
            ))}
          </svg>
        </DSCard>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
        <DSCard title="Alert Feed" subtitle="Nur das, was Du wirklich anschauen musst">
          {[
            ["WARN","orange","Gemini tool-calls: thought_signature fehlt in 2 Runs"],
            ["INFO","blue","Ollama Cloud Modellliste synchronisiert"],
            ["ERROR","red","Local Ollama healthcheck offline seit 18 min"],
          ].map(([k,c,t], i) => (
            <div key={i} style={{ display: "flex", gap: 12, padding: "10px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
              <span className={`pill pill--${c}`} style={{ minWidth: 56, justifyContent: "center" }}>{k}</span>
              <span style={{ fontSize: 13.5 }}>{t}</span>
            </div>
          ))}
        </DSCard>

        <DSCard title="Live Log Stream">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[
              "06:42:19  stage=simulation_rounds model=gpt-5.5 stream=true",
              "06:42:21  routing snapshot locked version=7",
              "06:42:24  budget check ok current=8.74 limit=25.00",
              "06:42:28  graph update edges=182 nodes=41",
            ].map((l, i) => (
              <div key={i} style={{
                background: "#0c0f14", color: "#d6e4ff",
                fontFamily: "var(--font-mono)", fontSize: 12.5,
                padding: "8px 12px", borderRadius: 6,
              }}>{l}</div>
            ))}
          </div>
        </DSCard>
      </div>
    </DSAppShell>
  );
};

window.DSA = DSA;
