/* Desktop screens (v3 — Apple Enterprise) */

const ABS = {};

// ─── Helpers ────────────────────────────────────────────────
function Avatar({ name, color, size = 32 }) {
  const initials = name.split(" ").map(s => s[0]).join("").slice(0,2).toUpperCase();
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.42, background: color }}>
      {initials}
    </span>
  );
}

function Sidebar({ active = "runs" }) {
  const Item = ({ id, ic, label, badge }) => (
    <div className={`sb-item ${active===id ? "active" : ""}`}>
      <span className="sb-icon"><Icon name={ic} size={16}/></span>
      <span style={{ flex: 1 }}>{label}</span>
      {badge && <span className="t-caption" style={{ color: active===id ? "rgba(255,255,255,0.85)" : "var(--text-tertiary)" }}>{badge}</span>}
    </div>
  );
  return (
    <div className="sb" style={{ width: 248, height: "100%", padding: "12px 0" }}>
      <div style={{ padding: "8px 16px 16px", display: "flex", alignItems: "center", gap: 8 }}>
        <GlyphV3 size={26}/>
        <span style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.018em" }}>Agora</span>
        <span className="pill" style={{ marginLeft: 4, padding: "0 6px", height: 18, fontSize: 9 }}>BETA</span>
      </div>
      <div style={{ padding: "0 16px 8px" }}>
        <div className="search">
          <Icon name="search" size={14}/>
          <span style={{ flex: 1, color: "var(--text-tertiary)" }}>Search…</span>
          <span className="t-caption">⌘K</span>
        </div>
      </div>
      <div className="sb-group">Workspace</div>
      <Item id="home" ic="home" label="Overview"/>
      <Item id="projects" ic="folder" label="Projects" badge="14"/>
      <Item id="runs" ic="bolt" label="Runs" badge="3 live"/>
      <Item id="reports" ic="report" label="Reports" badge="48"/>
      <div className="sb-group">Library</div>
      <Item id="personas" ic="users" label="Personas" badge="214"/>
      <Item id="graphs" ic="graph" label="Knowledge Graph"/>
      <Item id="evidence" ic="book" label="Evidence"/>
      <Item id="branches" ic="branch" label="Branches"/>
      <div className="sb-group">Account</div>
      <Item id="team" ic="user" label="Team"/>
      <Item id="settings" ic="settings" label="Settings"/>
      <div style={{ flex: 1 }}/>
      <div style={{ padding: 12, margin: "8px 12px", background: "var(--surface-elevated)", borderRadius: 10, boxShadow: "0 0 0 1px var(--hairline)" }}>
        <div className="hstack gap-2">
          <Avatar name="Alex Le" color="#0066CC" size={28}/>
          <div className="stack" style={{ flex: 1, minWidth: 0 }}>
            <span className="t-footnote" style={{ fontWeight: 600 }}>Alex Le</span>
            <span className="t-caption text-tertiary" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>acme.com · Admin</span>
          </div>
          <Icon name="chevronD" size={12}/>
        </div>
      </div>
    </div>
  );
}

function TopBar({ title, subtitle, status, actions }) {
  return (
    <div style={{
      height: 56, padding: "0 24px",
      borderBottom: "1px solid var(--hairline)",
      display: "flex", alignItems: "center", gap: 12,
      background: "var(--surface-base)",
    }}>
      <div className="stack gap-1" style={{ flex: 1 }}>
        <div className="hstack gap-2">
          <span className="t-headline">{title}</span>
          {status}
        </div>
        {subtitle && <span className="t-footnote text-secondary">{subtitle}</span>}
      </div>
      {actions}
    </div>
  );
}

// ─── 06 · Workspace Hub / Run Dashboard ─────────────────────
ABS.WorkspaceHub = () => {
  const runs = [
    { id: "RUN-0142", proj: "EU AI Act · Public Reaction", status: "live", round: "Round 12 / 16", progress: 0.74, personas: 214, started: "12 min ago", color: "#0066CC" },
    { id: "RUN-0141", proj: "Inflation Reduction · Workers", status: "queued", round: "Queued behind 2 jobs", progress: 0, personas: 96, started: "—", color: "#007A87" },
    { id: "RUN-0140", proj: "Climate Adapt Plan · Civic Forum", status: "done", round: "Completed 16 / 16", progress: 1, personas: 156, started: "1 h ago", color: "#248A3D" },
    { id: "RUN-0139", proj: "Healthcare Reform · Clinicians", status: "failed", round: "Failed at round 7", progress: 0.43, personas: 84, started: "3 h ago", color: "#C5292A" },
  ];

  const StatusPill = ({ s }) => ({
    live:   <span className="pill pill--blue"><span className="dot" style={{ background: "var(--accent)" }}></span>Live</span>,
    queued: <span className="pill pill--teal"><span className="dot"></span>Queued</span>,
    done:   <span className="pill pill--green"><span className="dot"></span>Done</span>,
    failed: <span className="pill pill--red"><span className="dot"></span>Failed</span>,
  })[s];

  return (
    <div style={{ height: "100%", display: "flex", background: "var(--surface-base)" }}>
      <Sidebar active="runs"/>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar
          title="Runs"
          subtitle="Multi-agent simulations across the workspace"
          actions={
            <div className="hstack gap-2">
              <button className="btn btn--secondary btn--sm"><Icon name="filter" size={12}/>Filter</button>
              <button className="btn btn--secondary btn--sm"><Icon name="download" size={12}/>Export</button>
              <button className="btn btn--primary btn--sm"><Icon name="plus" size={12}/>New run</button>
            </div>
          }
        />

        <div style={{ flex: 1, padding: 28, overflow: "auto", background: "var(--surface-canvas)" }}>
          {/* Hero metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 16, marginBottom: 24 }}>
            <div className="card card-pad" style={{ background: "linear-gradient(135deg, #0066CC, #004080)", color: "#fff", boxShadow: "var(--shadow-3)", border: 0 }}>
              <div className="t-section-head" style={{ color: "rgba(255,255,255,0.7)" }}>This week</div>
              <div style={{ fontSize: 44, lineHeight: "48px", fontWeight: 600, letterSpacing: "-0.022em", marginTop: 8, fontVariantNumeric: "tabular-nums" }}>
                12,840 <span style={{ fontSize: 18, opacity: 0.7, fontWeight: 500 }}>messages</span>
              </div>
              <div className="hstack gap-6" style={{ marginTop: 16 }}>
                <div className="stack gap-1">
                  <span className="t-caption" style={{ color: "rgba(255,255,255,0.6)" }}>RUNS</span>
                  <span style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>48</span>
                </div>
                <div className="stack gap-1">
                  <span className="t-caption" style={{ color: "rgba(255,255,255,0.6)" }}>PERSONAS</span>
                  <span style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>2,140</span>
                </div>
                <div className="stack gap-1">
                  <span className="t-caption" style={{ color: "rgba(255,255,255,0.6)" }}>AVG ROUND</span>
                  <span style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>4.2s</span>
                </div>
                <div className="stack gap-1">
                  <span className="t-caption" style={{ color: "rgba(255,255,255,0.6)" }}>TOKENS</span>
                  <span style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>1.4M</span>
                </div>
              </div>
            </div>

            {[
              { l: "Active runs", v: "3", sub: "2 live · 1 queued", color: "#0066CC", ic: "bolt" },
              { l: "Polarization", v: "0.62", sub: "Echo-chamber index", color: "#6E3CBC", ic: "graph" },
              { l: "Evidence coverage", v: "94%", sub: "Bound to source", color: "#248A3D", ic: "book" },
            ].map((m) => (
              <div key={m.l} className="card card-pad">
                <div className="hstack gap-3">
                  <span className="icon-chip icon-chip--lg" style={{ background: m.color + "1a", color: m.color }}>
                    <Icon name={m.ic} size={18}/>
                  </span>
                  <div className="stack gap-1" style={{ flex: 1 }}>
                    <span className="t-footnote text-secondary">{m.l}</span>
                    <span style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-0.018em", fontVariantNumeric: "tabular-nums" }}>{m.v}</span>
                  </div>
                </div>
                <span className="t-footnote text-secondary" style={{ marginTop: 12, display: "block" }}>{m.sub}</span>
              </div>
            ))}
          </div>

          {/* Runs table */}
          <div className="card" style={{ overflow: "hidden", padding: 0 }}>
            <div className="between" style={{ padding: "16px 20px", borderBottom: "1px solid var(--hairline)" }}>
              <div className="hstack gap-3">
                <span className="t-title-3">All runs</span>
                <span className="pill">{runs.length}</span>
              </div>
              <div className="hstack gap-2">
                <div className="segmented">
                  <div className="seg active">All</div>
                  <div className="seg">Mine</div>
                  <div className="seg">Live</div>
                  <div className="seg">Failed</div>
                </div>
              </div>
            </div>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 110 }}>ID</th>
                  <th>Project</th>
                  <th style={{ width: 140 }}>Status</th>
                  <th style={{ width: 200 }}>Progress</th>
                  <th style={{ width: 100 }}>Personas</th>
                  <th style={{ width: 120 }}>Started</th>
                  <th style={{ width: 60 }}></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td><span className="t-mono t-footnote text-secondary">{r.id}</span></td>
                    <td>
                      <div className="hstack gap-3">
                        <span className="icon-chip" style={{ background: r.color + "1a", color: r.color }}><Icon name="doc" size={14}/></span>
                        <div className="stack gap-1">
                          <span className="t-callout" style={{ fontWeight: 500 }}>{r.proj}</span>
                          <span className="t-footnote text-secondary">{r.round}</span>
                        </div>
                      </div>
                    </td>
                    <td><StatusPill s={r.status}/></td>
                    <td>
                      <div className="hstack gap-3">
                        <div className="bar" style={{ flex: 1, maxWidth: 140 }}>
                          <i style={{
                            width: `${r.progress * 100}%`,
                            background: r.status === "failed" ? "var(--status-red)" : r.status === "done" ? "var(--status-green)" : "var(--accent)",
                          }}/>
                        </div>
                        <span className="t-mono t-caption text-secondary" style={{ minWidth: 32 }}>{Math.round(r.progress*100)}%</span>
                      </div>
                    </td>
                    <td><span className="t-callout">{r.personas}</span></td>
                    <td><span className="t-footnote text-secondary">{r.started}</span></td>
                    <td><button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: 0 }}><Icon name="more"/></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── 07 · Persona Review (v0.9.0) ───────────────────────────
ABS.PersonaReview = () => {
  const personas = [
    { name: "Sofia Klein", role: "Privacy researcher", cluster: "Civic-tech", stance: 0.82, quality: 0.94, dup: 0.05, color: "#0066CC", flag: null },
    { name: "Marcus Weber", role: "SME founder · automotive", cluster: "Industry", stance: -0.32, quality: 0.91, dup: 0.08, color: "#B25000", flag: null },
    { name: "Aisha Okonkwo", role: "Civil rights lawyer", cluster: "Civic-tech", stance: 0.71, quality: 0.88, dup: 0.12, color: "#6E3CBC", flag: null },
    { name: "Lukas Bauer", role: "Senior policy advisor", cluster: "Policy", stance: 0.18, quality: 0.86, dup: 0.04, color: "#248A3D", flag: null },
    { name: "Yuki Tanaka", role: "Privacy researcher", cluster: "Civic-tech", stance: 0.79, quality: 0.62, dup: 0.71, color: "#0066CC", flag: "duplicate" },
    { name: "Hans Müller", role: "Retail SME", cluster: "Industry", stance: -0.45, quality: 0.48, dup: 0.10, color: "#B25000", flag: "thin" },
    { name: "Elena Rossi", role: "Journalist · Tech", cluster: "Media", stance: 0.34, quality: 0.81, dup: 0.06, color: "#007A87", flag: null },
  ];

  const StanceBar = ({ v }) => {
    const pct = ((v + 1) / 2) * 100;
    return (
      <div style={{ position: "relative", height: 8, background: "var(--gray-5)", borderRadius: 4, width: 140 }}>
        <div style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 1, background: "var(--gray-3)" }}/>
        {v >= 0
          ? <div style={{ position: "absolute", left: "50%", top: 0, height: "100%", width: `${pct - 50}%`, background: "var(--accent)", borderRadius: "0 4px 4px 0" }}/>
          : <div style={{ position: "absolute", right: "50%", top: 0, height: "100%", width: `${50 - pct}%`, background: "var(--status-orange)", borderRadius: "4px 0 0 4px" }}/>
        }
      </div>
    );
  };

  const QualityRing = ({ v, flag }) => {
    const c = v < 0.5 ? "var(--status-red)" : v < 0.8 ? "var(--status-orange)" : "var(--status-green)";
    const len = 2 * Math.PI * 12;
    return (
      <div className="hstack gap-2">
        <svg width="32" height="32" viewBox="0 0 32 32">
          <circle cx="16" cy="16" r="12" fill="none" stroke="var(--gray-5)" strokeWidth="3"/>
          <circle cx="16" cy="16" r="12" fill="none" stroke={c} strokeWidth="3"
            strokeDasharray={`${v * len} ${len}`} strokeDashoffset={len * 0.25}
            transform="rotate(-90 16 16)" strokeLinecap="round"/>
          <text x="16" y="19" textAnchor="middle" fontSize="9" fontWeight="600" fill="var(--text-primary)" style={{ fontVariantNumeric: "tabular-nums" }}>{Math.round(v*100)}</text>
        </svg>
        {flag === "duplicate" && <span className="pill pill--purple"><span className="dot"></span>Dup</span>}
        {flag === "thin"      && <span className="pill pill--orange"><span className="dot"></span>Thin</span>}
      </div>
    );
  };

  return (
    <div style={{ height: "100%", display: "flex", background: "var(--surface-base)" }}>
      <Sidebar active="personas"/>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar
          title="EU AI Act · Public Reaction"
          subtitle="Step 03 of 5 · Persona Review"
          status={<span className="pill pill--blue"><span className="dot" style={{ background: "var(--accent)" }}></span>Awaiting approval</span>}
          actions={
            <div className="hstack gap-2">
              <button className="btn btn--secondary btn--sm">Reject all flagged</button>
              <button className="btn btn--tinted btn--sm">Auto-fix · 3 issues</button>
              <button className="btn btn--primary btn--sm">Approve & continue</button>
            </div>
          }
        />

        <div style={{ flex: 1, padding: 28, overflow: "auto", background: "var(--surface-canvas)" }}>
          {/* Step indicator */}
          <div className="card card-pad" style={{ marginBottom: 20 }}>
            <div className="hstack gap-3" style={{ overflow: "hidden" }}>
              {[
                { n: "01", l: "Upload",  done: true },
                { n: "02", l: "Build graph", done: true },
                { n: "03", l: "Review personas", current: true },
                { n: "04", l: "Run discussion" },
                { n: "05", l: "Report" },
              ].map((s, i, arr) => (
                <React.Fragment key={s.n}>
                  <div className="hstack gap-2">
                    <span style={{
                      width: 26, height: 26, borderRadius: 13,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: s.done ? "var(--status-green)" : s.current ? "var(--accent)" : "var(--surface-inset)",
                      color: s.done || s.current ? "#fff" : "var(--text-secondary)",
                      fontSize: 11, fontWeight: 600, fontVariantNumeric: "tabular-nums",
                      boxShadow: s.current ? "0 0 0 4px var(--accent-tint-bg)" : "none",
                    }}>{s.done ? <Icon name="check" size={12}/> : s.n}</span>
                    <span className="t-callout" style={{ fontWeight: s.current ? 600 : 500, color: s.done || s.current ? "var(--text-primary)" : "var(--text-secondary)" }}>{s.l}</span>
                  </div>
                  {i < arr.length - 1 && <div style={{ flex: 1, height: 1, background: s.done ? "var(--status-green)" : "var(--separator)" }}/>}
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* Quality summary */}
          <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div className="card card-pad">
              <div className="t-section-head" style={{ marginBottom: 8 }}>Population balance</div>
              <div className="t-title-3" style={{ marginBottom: 12 }}>Stance distribution</div>
              <div style={{ display: "flex", gap: 2, height: 28, borderRadius: 6, overflow: "hidden" }}>
                <div style={{ width: "12%", background: "#C5292A" }} title="Strongly oppose"/>
                <div style={{ width: "16%", background: "#E8945C" }} title="Oppose"/>
                <div style={{ width: "22%", background: "#D1D1D6" }} title="Neutral"/>
                <div style={{ width: "26%", background: "#5BB1FF" }} title="Support"/>
                <div style={{ width: "24%", background: "#0066CC" }} title="Strongly support"/>
              </div>
              <div className="hstack" style={{ justifyContent: "space-between", marginTop: 8 }}>
                <span className="t-caption">Strongly oppose · 12%</span>
                <span className="t-caption">Neutral · 22%</span>
                <span className="t-caption">Strongly support · 24%</span>
              </div>
              <div className="hstack gap-3" style={{ marginTop: 16 }}>
                <span className="pill pill--green"><span className="dot"></span>Echo-chamber risk: low</span>
                <span className="t-footnote text-secondary">Polarization index 0.41 · within target band</span>
              </div>
            </div>
            {[
              { l: "Personas",  v: "214",  sub: "of 240 generated" },
              { l: "Avg quality", v: "0.86", sub: "Heuristic score" },
              { l: "Issues",    v: "3",  sub: "Need review", color: "var(--status-orange)" },
            ].map((m) => (
              <div key={m.l} className="card card-pad" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <span className="t-section-head">{m.l}</span>
                <span style={{ fontSize: 36, fontWeight: 600, letterSpacing: "-0.022em", fontVariantNumeric: "tabular-nums", color: m.color || "var(--text-primary)" }}>{m.v}</span>
                <span className="t-footnote text-secondary">{m.sub}</span>
              </div>
            ))}
          </div>

          {/* Persona table */}
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="between" style={{ padding: "16px 20px", borderBottom: "1px solid var(--hairline)" }}>
              <div className="hstack gap-3">
                <span className="t-title-3">Personas</span>
                <span className="pill">214</span>
                <span className="pill pill--orange"><span className="dot"></span>3 flagged</span>
              </div>
              <div className="hstack gap-2">
                <div className="search" style={{ width: 220 }}>
                  <Icon name="search" size={14}/>
                  <span style={{ color: "var(--text-tertiary)" }}>Search personas…</span>
                </div>
                <button className="btn btn--secondary btn--sm"><Icon name="filter" size={12}/>Cluster</button>
                <button className="btn btn--secondary btn--sm"><Icon name="sliders" size={12}/>View</button>
              </div>
            </div>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 32 }}><input type="checkbox" defaultChecked/></th>
                  <th>Persona</th>
                  <th style={{ width: 120 }}>Cluster</th>
                  <th style={{ width: 180 }}>Stance</th>
                  <th style={{ width: 140 }}>Quality</th>
                  <th style={{ width: 80 }}>Dup</th>
                  <th style={{ width: 100 }}></th>
                </tr>
              </thead>
              <tbody>
                {personas.map((p) => (
                  <tr key={p.name} style={{ background: p.flag ? "rgba(178,80,0,0.04)" : "transparent" }}>
                    <td><input type="checkbox" defaultChecked={!p.flag}/></td>
                    <td>
                      <div className="hstack gap-3">
                        <Avatar name={p.name} color={p.color}/>
                        <div className="stack gap-1">
                          <span className="t-callout" style={{ fontWeight: 500 }}>{p.name}</span>
                          <span className="t-footnote text-secondary">{p.role}</span>
                        </div>
                      </div>
                    </td>
                    <td><span className="pill" style={{ background: p.color + "1a", color: p.color }}>{p.cluster}</span></td>
                    <td><StanceBar v={p.stance}/></td>
                    <td><QualityRing v={p.quality} flag={p.flag}/></td>
                    <td><span className="t-mono t-footnote" style={{ color: p.dup > 0.4 ? "var(--status-purple)" : "var(--text-secondary)" }}>{p.dup.toFixed(2)}</span></td>
                    <td>
                      {p.flag === "duplicate" ? (
                        <button className="btn btn--tinted btn--sm">Merge</button>
                      ) : p.flag === "thin" ? (
                        <button className="btn btn--tinted btn--sm">Enrich</button>
                      ) : (
                        <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: 0 }}><Icon name="more"/></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── 08 · Graph Workspace ───────────────────────────────────
ABS.GraphWorkspace = () => {
  // Node positions for a fictional knowledge graph
  const nodes = [
    { id: "ai-act",      label: "EU AI Act",        x: 50, y: 38, r: 22, kind: "doc"   },
    { id: "high-risk",   label: "High-Risk Systems",x: 24, y: 22, r: 14, kind: "topic" },
    { id: "biometric",   label: "Biometric ID",     x: 18, y: 50, r: 10, kind: "topic" },
    { id: "transparency",label: "Transparency",     x: 38, y: 70, r: 12, kind: "topic" },
    { id: "redress",     label: "Redress",          x: 64, y: 78, r: 10, kind: "topic" },
    { id: "innovation",  label: "Innovation",       x: 78, y: 58, r: 12, kind: "topic" },
    { id: "smes",        label: "SMEs",             x: 86, y: 30, r: 10, kind: "actor" },
    { id: "regulators",  label: "Regulators",       x: 70, y: 16, r: 12, kind: "actor" },
    { id: "civic",       label: "Civic groups",     x: 44, y: 12, r: 10, kind: "actor" },
  ];
  const edges = [
    ["ai-act","high-risk"], ["ai-act","biometric"], ["ai-act","transparency"], ["ai-act","redress"], ["ai-act","innovation"],
    ["ai-act","smes"], ["ai-act","regulators"], ["ai-act","civic"],
    ["high-risk","biometric"], ["transparency","redress"], ["innovation","smes"], ["regulators","civic"],
  ];
  const kindColor = { doc: "#0066CC", topic: "#6E3CBC", actor: "#248A3D" };

  const getNode = (id) => nodes.find((n) => n.id === id);

  return (
    <div style={{ height: "100%", display: "flex", background: "var(--surface-base)" }}>
      <Sidebar active="graphs"/>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar
          title="EU AI Act · Knowledge Graph"
          subtitle="124 entities · 318 relations · build complete"
          status={<span className="pill pill--green"><span className="dot"></span>Built</span>}
          actions={
            <div className="hstack gap-2">
              <div className="segmented">
                <div className="seg active">Force</div>
                <div className="seg">Cluster</div>
                <div className="seg">Hierarchy</div>
              </div>
              <button className="btn btn--secondary btn--sm"><Icon name="download" size={12}/>Export</button>
            </div>
          }
        />

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Graph canvas */}
          <div style={{ flex: 1, position: "relative", background: "var(--surface-canvas)", overflow: "hidden" }}>
            {/* Subtle dot pattern */}
            <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, opacity: 0.7 }}>
              <defs>
                <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">
                  <circle cx="1.5" cy="1.5" r="1" fill="rgba(60,60,67,0.15)"/>
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#dots)"/>
            </svg>

            {/* Graph */}
            <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{
              position: "absolute", inset: 0, width: "100%", height: "100%",
            }}>
              {/* Edges */}
              {edges.map(([a, b], i) => {
                const na = getNode(a), nb = getNode(b);
                return (
                  <line key={i} x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
                    stroke="rgba(60,60,67,0.22)" strokeWidth="0.25"/>
                );
              })}
              {/* Highlighted edge */}
              <line x1={getNode("ai-act").x} y1={getNode("ai-act").y}
                    x2={getNode("transparency").x} y2={getNode("transparency").y}
                    stroke="#0066CC" strokeWidth="0.5"/>
              {/* Nodes */}
              {nodes.map((n) => (
                <g key={n.id}>
                  <circle cx={n.x} cy={n.y} r={n.r / 8 + 1.6}
                    fill={kindColor[n.kind]} opacity="0.12"/>
                  <circle cx={n.x} cy={n.y} r={n.r / 10}
                    fill="white" stroke={kindColor[n.kind]} strokeWidth="0.5"/>
                  <circle cx={n.x} cy={n.y} r={n.r / 18}
                    fill={kindColor[n.kind]}/>
                </g>
              ))}
              {/* Labels */}
              {nodes.map((n) => (
                <text key={n.id + "-l"} x={n.x} y={n.y + n.r / 8 + 3.4}
                  textAnchor="middle" fontSize="2" fontWeight="600"
                  fill="var(--text-primary)"
                  style={{ fontFamily: "var(--font-sans)" }}>
                  {n.label}
                </text>
              ))}
            </svg>

            {/* Floating glass toolbar */}
            <div className="glass" style={{
              position: "absolute", left: "50%", bottom: 24, transform: "translateX(-50%)",
              borderRadius: 24, padding: "8px 12px", display: "flex", alignItems: "center", gap: 8,
            }}>
              <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: 0 }}><Icon name="plus" size={14}/></button>
              <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: 0 }}><Icon name="refresh" size={14}/></button>
              <div style={{ width: 1, height: 20, background: "var(--separator)" }}/>
              <span className="t-mono t-caption text-secondary" style={{ minWidth: 60, textAlign: "center" }}>78%</span>
              <div style={{ width: 1, height: 20, background: "var(--separator)" }}/>
              <span className="pill pill--blue"><span className="dot" style={{ background: "var(--accent)" }}></span>Round 12</span>
              <button className="btn btn--primary btn--sm"><Icon name="play" size={12}/>Replay</button>
            </div>

            {/* Temporal slider — bottom */}
            <div style={{
              position: "absolute", left: 24, right: 24, bottom: 96,
              padding: "12px 16px",
              background: "var(--surface-translucent)",
              backdropFilter: "saturate(180%) blur(20px)",
              WebkitBackdropFilter: "saturate(180%) blur(20px)",
              borderRadius: 14,
              boxShadow: "0 0 0 1px var(--hairline), var(--shadow-2)",
            }}>
              <div className="between" style={{ marginBottom: 8 }}>
                <span className="t-section-head">Temporal · Round 12 of 16</span>
                <span className="t-caption text-secondary">+3 entities · +18 relations since round 8</span>
              </div>
              <div style={{ position: "relative", height: 32 }}>
                {/* Track */}
                <div style={{ position: "absolute", left: 0, right: 0, top: 14, height: 4, borderRadius: 2, background: "var(--gray-5)" }}/>
                <div style={{ position: "absolute", left: 0, top: 14, height: 4, borderRadius: 2, background: "var(--accent)", width: "72%" }}/>
                {/* Round ticks */}
                {Array.from({ length: 16 }).map((_, i) => (
                  <div key={i} style={{
                    position: "absolute", left: `${(i / 15) * 100}%`, top: 12, width: 1, height: 8,
                    background: i <= 11 ? "var(--accent)" : "var(--gray-3)", transform: "translateX(-0.5px)",
                  }}/>
                ))}
                {/* Bridge agent markers */}
                {[3, 7, 11].map((i) => (
                  <div key={"b"+i} style={{
                    position: "absolute", left: `${(i / 15) * 100}%`, top: 4, width: 8, height: 8,
                    borderRadius: "50%", background: "#6E3CBC",
                    transform: "translateX(-4px)",
                    boxShadow: "0 0 0 3px rgba(110,60,188,0.18)",
                  }}/>
                ))}
                {/* Thumb */}
                <div style={{
                  position: "absolute", left: "72%", top: 6, width: 20, height: 20, borderRadius: 10,
                  background: "white", boxShadow: "0 1px 3px rgba(0,0,0,0.18), 0 0 0 0.5px rgba(0,0,0,0.06)",
                  transform: "translateX(-10px)",
                }}/>
              </div>
              <div className="hstack gap-3" style={{ marginTop: 4 }}>
                <span className="t-caption">R0</span>
                <div style={{ flex: 1 }}/>
                <span className="hstack gap-1"><span style={{ width: 8, height: 8, borderRadius: 4, background: "#6E3CBC" }}></span><span className="t-caption">Bridge agent appears</span></span>
                <div style={{ flex: 1 }}/>
                <span className="t-caption">R16</span>
              </div>
            </div>
          </div>

          {/* Inspector panel */}
          <div style={{
            width: 320, borderLeft: "1px solid var(--hairline)",
            background: "var(--surface-base)", overflow: "auto",
            display: "flex", flexDirection: "column",
          }}>
            <div style={{ padding: "20px 20px 12px" }}>
              <span className="t-section-head">Selected entity</span>
              <div className="hstack gap-3" style={{ marginTop: 12 }}>
                <span className="icon-chip icon-chip--lg icon-chip--blue"><Icon name="doc" size={18}/></span>
                <div className="stack gap-1">
                  <span className="t-title-3">Transparency</span>
                  <span className="t-footnote text-secondary">Topic · cluster Civic-tech</span>
                </div>
              </div>
            </div>

            <div className="divider"/>

            <div style={{ padding: "16px 20px" }}>
              <div className="t-section-head" style={{ marginBottom: 12 }}>Confidence</div>
              <div className="hstack gap-3">
                <span style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-0.018em", fontVariantNumeric: "tabular-nums" }}>0.91</span>
                <div className="stack gap-1" style={{ flex: 1 }}>
                  <div className="bar bar--green"><i style={{ width: "91%" }}/></div>
                  <span className="t-footnote text-secondary">Bound to 4 evidence spans</span>
                </div>
              </div>
            </div>

            <div className="divider"/>

            <div style={{ padding: "16px 20px" }}>
              <div className="t-section-head" style={{ marginBottom: 12 }}>Evidence</div>
              <div className="stack gap-3">
                {[
                  { src: "Article 13", page: "p. 14", text: "High-risk AI systems shall be designed and developed in such a way that their operation is sufficiently transparent…", conf: 0.96 },
                  { src: "Recital 47", page: "p. 8",  text: "Transparency obligations should apply to systems that interact with natural persons…", conf: 0.88 },
                ].map((e, i) => (
                  <div key={i} style={{ padding: 12, background: "var(--surface-canvas)", borderRadius: 10 }}>
                    <div className="between" style={{ marginBottom: 6 }}>
                      <span className="t-footnote" style={{ fontWeight: 600 }}>{e.src}</span>
                      <span className="t-mono t-caption text-secondary">{e.page} · {e.conf.toFixed(2)}</span>
                    </div>
                    <p className="t-footnote" style={{ margin: 0, color: "var(--text-secondary)", lineHeight: 1.5 }}>"{e.text}"</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="divider"/>

            <div style={{ padding: "16px 20px" }}>
              <div className="t-section-head" style={{ marginBottom: 12 }}>Connected (8)</div>
              <div className="stack gap-2">
                {[
                  { l: "EU AI Act", k: "doc", w: 0.92 },
                  { l: "Redress",   k: "topic", w: 0.74 },
                  { l: "Civic groups", k: "actor", w: 0.61 },
                  { l: "Regulators",   k: "actor", w: 0.58 },
                ].map((c) => (
                  <div key={c.l} className="hstack gap-3" style={{ padding: "8px 0" }}>
                    <span style={{ width: 8, height: 8, borderRadius: 4, background: kindColor[c.k] }}/>
                    <span className="t-callout" style={{ flex: 1 }}>{c.l}</span>
                    <span className="t-mono t-caption text-secondary">{c.w.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="divider"/>

            <div className="hstack gap-2" style={{ padding: 16, marginTop: "auto" }}>
              <button className="btn btn--secondary btn--sm" style={{ flex: 1 }}>Trace path</button>
              <button className="btn btn--tinted btn--sm" style={{ flex: 1 }}>Open in graph</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── 09 · Report Viewer ─────────────────────────────────────
ABS.Report = () => {
  return (
    <div style={{ height: "100%", display: "flex", background: "var(--surface-base)" }}>
      <Sidebar active="reports"/>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar
          title="Report · EU AI Act · Public Reaction"
          subtitle="Run #0140 · 16 rounds · 156 personas · generated 1 h ago"
          status={<span className="pill pill--green"><span className="dot"></span>v3 · Final</span>}
          actions={
            <div className="hstack gap-2">
              <button className="btn btn--secondary btn--sm"><Icon name="branch" size={12}/>Branch</button>
              <button className="btn btn--secondary btn--sm">Compare</button>
              <button className="btn btn--tinted btn--sm"><Icon name="download" size={12}/>Export</button>
              <button className="btn btn--primary btn--sm">Share</button>
            </div>
          }
        />

        <div style={{ flex: 1, display: "flex", minHeight: 0, background: "var(--surface-canvas)" }}>
          {/* Report canvas */}
          <div style={{ flex: 1, padding: 32, overflow: "auto" }}>
            <div style={{ maxWidth: 760, margin: "0 auto" }}>
              {/* Headline metric */}
              <div className="card card-pad-lg" style={{ marginBottom: 24, padding: 32 }}>
                <span className="t-section-head">Executive summary</span>
                <h1 className="t-display" style={{ margin: "16px 0 20px", fontSize: 40, lineHeight: "44px" }}>
                  Civic groups and SMEs converge on the need for clearer transparency rules — but diverge sharply on enforcement.
                </h1>
                <div className="hstack gap-6" style={{ marginTop: 16, paddingTop: 20, borderTop: "1px solid var(--separator)" }}>
                  <div className="metric"><span className="v">156</span><span className="l">Personas</span></div>
                  <div className="metric"><span className="v">12,840</span><span className="l">Messages</span></div>
                  <div className="metric"><span className="v">0.62</span><span className="l">Polarization</span></div>
                  <div className="metric"><span className="v">94%</span><span className="l">Evidence-bound</span></div>
                </div>
              </div>

              {/* Key findings */}
              <div className="t-section-head" style={{ marginBottom: 12 }}>Key findings</div>
              <div className="stack gap-3" style={{ marginBottom: 28 }}>
                {[
                  { n: "01", t: "Transparency obligations broadly accepted",  d: "73% of personas across all clusters supported Article 13 requirements. Civic-tech personas wanted stronger language; SME personas wanted clearer thresholds.", conf: 0.94 },
                  { n: "02", t: "Enforcement is the fault-line", d: "Polarization spikes when discussion shifts from principles to fines. Industry cluster opposes flat-rate fines; civic cluster wants escalation.", conf: 0.81 },
                  { n: "03", t: "SMEs demand sandbox guidance", d: "82% of SME personas requested dedicated guidance and sandbox access before high-risk deployment. Cross-cluster bridge formed around this point in round 11.", conf: 0.88 },
                ].map((f) => (
                  <div key={f.n} className="card card-pad" style={{ display: "flex", gap: 20 }}>
                    <span className="t-mono" style={{ fontSize: 32, fontWeight: 600, color: "var(--accent)", letterSpacing: "-0.018em", minWidth: 48 }}>{f.n}</span>
                    <div className="stack gap-2" style={{ flex: 1 }}>
                      <div className="between">
                        <span className="t-headline">{f.t}</span>
                        <span className="pill" style={{
                          background: f.conf > 0.9 ? "var(--status-green-bg)" : "var(--status-orange-bg)",
                          color:      f.conf > 0.9 ? "var(--status-green)"    : "var(--status-orange)",
                        }}><Icon name="check" size={12}/>Confidence {f.conf.toFixed(2)}</span>
                      </div>
                      <p className="t-body" style={{ margin: 0, color: "var(--text-secondary)" }}>{f.d}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Polarization chart */}
              <div className="card card-pad" style={{ marginBottom: 28 }}>
                <div className="between" style={{ marginBottom: 16 }}>
                  <span className="t-headline">Polarization across rounds</span>
                  <span className="pill pill--purple"><span className="dot"></span>Echo-chamber index</span>
                </div>
                <svg viewBox="0 0 600 160" width="100%" height="160" preserveAspectRatio="none">
                  {/* Grid */}
                  {[0, 40, 80, 120].map((y) => (
                    <line key={y} x1="0" x2="600" y1={y} y2={y} stroke="var(--separator)" strokeDasharray="2 4"/>
                  ))}
                  {/* Area */}
                  <path d="M 0 130 L 50 110 L 100 100 L 150 80 L 200 70 L 250 60 L 300 70 L 350 65 L 400 50 L 450 60 L 500 45 L 550 35 L 600 30 L 600 160 L 0 160 Z"
                    fill="url(#area)" opacity="0.5"/>
                  <path d="M 0 130 L 50 110 L 100 100 L 150 80 L 200 70 L 250 60 L 300 70 L 350 65 L 400 50 L 450 60 L 500 45 L 550 35 L 600 30"
                    fill="none" stroke="#6E3CBC" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <defs>
                    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#6E3CBC"/>
                      <stop offset="1" stopColor="#6E3CBC" stopOpacity="0"/>
                    </linearGradient>
                  </defs>
                  {/* Marker for round 11 */}
                  <line x1="400" y1="0" x2="400" y2="160" stroke="var(--accent)" strokeWidth="1" strokeDasharray="2 2"/>
                  <circle cx="400" cy="50" r="5" fill="white" stroke="var(--accent)" strokeWidth="2"/>
                </svg>
                <div className="hstack gap-6" style={{ marginTop: 12 }}>
                  <span className="t-footnote text-secondary">R0</span>
                  <span className="t-footnote text-secondary" style={{ flex: 1, textAlign: "center" }}>Bridge formed at round 11 (vertical marker) reduced polarization by 0.18.</span>
                  <span className="t-footnote text-secondary">R16</span>
                </div>
              </div>

              {/* Quote / persona excerpt */}
              <div className="card card-pad-lg" style={{ marginBottom: 28, background: "var(--accent-tint-bg)", boxShadow: "0 0 0 1px rgba(0,102,204,0.18)" }}>
                <div className="hstack gap-4">
                  <Avatar name="Sofia Klein" color="#0066CC" size={56}/>
                  <div className="stack gap-3" style={{ flex: 1 }}>
                    <span className="t-title-3" style={{ color: "var(--accent-tint-text)" }}>"Transparency without redress is just a label. We need an enforcement ladder that scales with risk — sandbox first, fines later."</span>
                    <div className="hstack gap-2">
                      <span className="t-footnote" style={{ fontWeight: 600 }}>Sofia Klein</span>
                      <span className="t-footnote text-secondary">Privacy researcher · Civic-tech · Round 11</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right rail · TOC */}
          <div style={{
            width: 240, borderLeft: "1px solid var(--hairline)",
            background: "var(--surface-base)", padding: 20,
          }}>
            <span className="t-section-head">On this page</span>
            <div className="stack gap-1" style={{ marginTop: 12 }}>
              {[
                ["Executive summary", true],
                ["Key findings", false],
                ["Polarization timeline", false],
                ["Cluster dynamics", false],
                ["Bridge agents", false],
                ["Counterfactuals", false],
                ["Methodology", false],
              ].map(([l, active]) => (
                <div key={l} style={{
                  padding: "6px 10px",
                  borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                  fontSize: 13, fontWeight: active ? 600 : 400,
                  color: active ? "var(--text-primary)" : "var(--text-secondary)",
                }}>{l}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

window.ABS = ABS;
window.Avatar = Avatar;
