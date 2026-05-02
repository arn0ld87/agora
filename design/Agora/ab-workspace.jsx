/* Workspace shell artboard: Sidebar + Topbar + Stepper */

const ABWorkspace = {};

ABWorkspace.Shell = () => (
  <div className="ab" style={{ display: "block" }}>
    <div className="ws">
      <aside className="ws-side">
        <div className="brand">
          <AgoraLogo size={22} />
        </div>
        <div className="nav-section">
          <div className="nav-section-label">Pipeline</div>
          <div className="nav-link is-active"><span><span className="idx">№ 03</span> &nbsp; Simulation</span><span className="end"><span className="status-dot status-dot--running"></span></span></div>
          <div className="nav-link"><span><span className="idx">№ 01</span> &nbsp; Graph Build</span><span className="end" style={{ color: "var(--status-success)" }}>✓</span></div>
          <div className="nav-link"><span><span className="idx">№ 02</span> &nbsp; Environment</span><span className="end" style={{ color: "var(--status-success)" }}>✓</span></div>
          <div className="nav-link"><span><span className="idx">№ 04</span> &nbsp; Report</span><span className="end">—</span></div>
          <div className="nav-link"><span><span className="idx">№ 05</span> &nbsp; Interaction</span><span className="end">—</span></div>
        </div>
        <div className="nav-section">
          <div className="nav-section-label">Werkstatt</div>
          <div className="nav-link"><span>Persona-Bibliothek</span><span className="end">847</span></div>
          <div className="nav-link"><span>Verlauf</span><span className="end">12</span></div>
          <div className="nav-link"><span>Modelle</span></div>
          <div className="nav-link"><span>Audit-Log</span></div>
        </div>
        <div className="nav-section">
          <div className="nav-section-label">System</div>
          <div className="nav-link"><span>Neo4j</span><span className="end" style={{ color: "var(--status-success)" }}>● 5.18</span></div>
          <div className="nav-link"><span>Ollama</span><span className="end" style={{ color: "var(--status-success)" }}>● CLOUD</span></div>
          <div className="nav-link"><span>Redis</span><span className="end" style={{ color: "var(--status-warn)" }}>● FILE</span></div>
        </div>
        <div className="ws-foot">
          <span className="dot-glow"></span>
          <span>v0.6.1 · ALPHA</span>
        </div>
      </aside>
      <main className="ws-main">
        <div className="ws-topbar">
          <div className="crumbs">
            <span>SIM-04F2</span><span className="sep">/</span>
            <span>EU-AI-ACT-DOSSIER</span><span className="sep">/</span>
            <span className="here">SIMULATION</span>
          </div>
          <div className="row" style={{ gap: 10 }}>
            <div className="coord">
              <span>52.5200°N</span><span className="sep">·</span>
              <span>13.4050°E</span><span className="sep">·</span>
              <span className="accent">ROUND 13 / 24</span>
            </div>
            <button className="btn btn--ghost btn--sm">⌘K Suchen</button>
            <button className="btn btn--secondary btn--sm">Pause</button>
            <button className="btn btn--primary btn--sm">Stop <span className="glyph">▪</span></button>
          </div>
        </div>
        <div className="ws-stepper">
          <div className="ws-step is-done">
            <div className="head"><span className="n">01</span> ✓ GRAPH BUILD</div>
            <div className="lbl">Wissensgraph</div>
            <div className="meta-line">214 Knoten · 1.482 Kanten</div>
          </div>
          <div className="ws-step is-done">
            <div className="head"><span className="n">02</span> ✓ ENV SETUP</div>
            <div className="lbl">Personas</div>
            <div className="meta-line">214 erzeugt · 14 Cluster</div>
          </div>
          <div className="ws-step is-active">
            <div className="head"><span className="n">03</span> · LIVE · ROUND 13</div>
            <div className="lbl">Simulation</div>
            <div className="meta-line">04:12 · 1.847 LLM-Calls</div>
          </div>
          <div className="ws-step is-future">
            <div className="head"><span className="n">04</span> WARTET</div>
            <div className="lbl">Report</div>
            <div className="meta-line">—</div>
          </div>
          <div className="ws-step is-future">
            <div className="head"><span className="n">05</span> WARTET</div>
            <div className="lbl">Interaction</div>
            <div className="meta-line">—</div>
          </div>
        </div>
        <div className="ws-content">
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 24, height: "100%" }}>
            <div className="panel">
              <div className="panel-head">
                <div className="title-line">
                  <span className="t-kicker t-kicker--accent">№ KARTOGRAPHIE</span>
                  <span className="t-subtitle" style={{ fontSize: 16 }}>Wissensgraph · Round 13</span>
                </div>
                <div className="row" style={{ gap: 8 }}>
                  <div className="segmented">
                    <button className="seg">Liste</button>
                    <button className="seg is-active">Graph</button>
                    <button className="seg">Diff</button>
                  </div>
                </div>
              </div>
              <div className="panel-body" style={{ padding: 0 }}>
                <div className="graph-canvas">
                  <svg viewBox="0 0 600 320" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
                    <line x1="120" y1="80" x2="280" y2="160" stroke="var(--rule-strong)" strokeWidth="1" />
                    <line x1="280" y1="160" x2="460" y2="100" stroke="var(--rule-strong)" strokeWidth="1" />
                    <line x1="280" y1="160" x2="200" y2="240" stroke="var(--plasma-400)" strokeWidth="1.5" />
                    <line x1="280" y1="160" x2="420" y2="240" stroke="var(--rule-strong)" strokeWidth="1" />
                    <line x1="120" y1="80" x2="200" y2="240" stroke="var(--rule)" strokeWidth="1" />
                    <line x1="460" y1="100" x2="420" y2="240" stroke="var(--rule)" strokeWidth="1" />
                    <line x1="280" y1="160" x2="500" y2="200" stroke="var(--accent)" strokeWidth="1.5" />
                    <circle cx="120" cy="80" r="6" fill="var(--mono-50)" />
                    <circle cx="460" cy="100" r="6" fill="var(--mono-50)" />
                    <circle cx="200" cy="240" r="5" fill="var(--plasma-400)" />
                    <circle cx="420" cy="240" r="5" fill="var(--mono-300)" />
                    <circle cx="280" cy="160" r="10" fill="var(--accent)" />
                    <circle cx="280" cy="160" r="14" fill="none" stroke="var(--accent)" strokeWidth="0.5" opacity="0.5" />
                    <circle cx="500" cy="200" r="5" fill="var(--accent)" />
                    <text x="294" y="156" fontFamily="Geist Mono" fontSize="10" fill="var(--accent)" letterSpacing="1">EU-AI-ACT</text>
                    <text x="130" y="76" fontFamily="Geist Mono" fontSize="10" fill="var(--mono-400)">KOMMISSION</text>
                    <text x="208" y="256" fontFamily="Geist Mono" fontSize="10" fill="var(--plasma-400)">PERSONA-47</text>
                  </svg>
                </div>
              </div>
              <div className="panel-foot">
                <span className="meta-mono">14 CLUSTER · 3 BRIDGES · ECHO-INDEX 0.42</span>
                <span className="row" style={{ gap: 8 }}>
                  <span className="badge"><span className="dot"></span>ENTITY</span>
                  <span className="badge badge--accent">FOCUS</span>
                  <span className="badge badge--plasma">SELECTED</span>
                </span>
              </div>
            </div>

            <div className="col" style={{ gap: 16 }}>
              <div className="panel">
                <div className="panel-head">
                  <div className="title-line">
                    <span className="t-kicker">SIM-RUN · LIVE</span>
                  </div>
                  <span className="meta-mono" style={{ color: "var(--accent)" }}>04:12</span>
                </div>
                <div className="panel-body" style={{ padding: 16 }}>
                  <div className="meta-mono" style={{ marginBottom: 6 }}>FORTSCHRITT · 13 / 24 RUNDEN</div>
                  <div className="progress"><div className="bar" style={{ width: "54%" }}></div></div>
                  <div className="row" style={{ gap: 24, marginTop: 16 }}>
                    <div><div className="meta-mono">PERSONAS</div><div className="t-subtitle" style={{ fontSize: 24 }}>214</div></div>
                    <div><div className="meta-mono">POSTS</div><div className="t-subtitle" style={{ fontSize: 24 }}>1.482</div></div>
                    <div><div className="meta-mono">LLM CALLS</div><div className="t-subtitle" style={{ fontSize: 24 }}>1.847</div></div>
                  </div>
                </div>
              </div>
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title-line"><span className="t-kicker">CONSOLE · OASIS</span></div>
                  <span className="meta-mono">TAIL · 12 ZEILEN</span>
                </div>
                <div className="panel-body" style={{ padding: 0 }}>
                  <div className="log" style={{ border: 0, borderRadius: 0, maxHeight: 220 }}>
                    <div><span className="ts">14:02:18</span> <span className="lvl-info">INFO</span> &nbsp;ROUND_START round=13 personas=214</div>
                    <div><span className="ts">14:02:19</span> <span className="lvl-ok">OK</span> &nbsp;&nbsp;&nbsp;<span className="agent">persona-47</span> POST id=p1847</div>
                    <div><span className="ts">14:02:21</span> <span className="lvl-ok">OK</span> &nbsp;&nbsp;&nbsp;<span className="agent">persona-112</span> REPLY to=p1847</div>
                    <div><span className="ts">14:02:23</span> <span className="lvl-warn">WARN</span> ollama latency=2400ms (retry=1)</div>
                    <div><span className="ts">14:02:25</span> <span className="lvl-ok">OK</span> &nbsp;&nbsp;&nbsp;<span className="agent">persona-09</span> LIKE p1847</div>
                    <div><span className="ts">14:02:26</span> <span className="lvl-info">INFO</span> &nbsp;graph.add_edge persona-47→persona-112</div>
                    <div><span className="ts">14:02:28</span> <span className="lvl-err">ERR</span> &nbsp;json_mode malformed (retry=2)</div>
                    <div><span className="ts">14:02:30</span> <span className="lvl-ok">OK</span> &nbsp;&nbsp;&nbsp;recovered after 2 retries</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
);

window.ABWorkspace = ABWorkspace;
