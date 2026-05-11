/* Controls: Buttons · Inputs · Lists · Tables (v3 — Apple Enterprise) */

const ABC = {};

// Tiny stroke icon set (SF Symbols-inspired, currentColor)
function Icon({ name, size = 16, stroke = 1.6 }) {
  const p = (d) => <path d={d} stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" fill="none"/>;
  const map = {
    chevron:    p("M6 4 L12 10 L6 16"),
    chevronD:   p("M4 7 L10 13 L16 7"),
    plus:       p("M10 4 V16 M4 10 H16"),
    search:     <g><circle cx="9" cy="9" r="5" stroke="currentColor" strokeWidth={stroke} fill="none"/><path d="M13 13 L17 17" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round"/></g>,
    play:       <path d="M5 3 L17 10 L5 17 Z" fill="currentColor"/>,
    pause:      <g><rect x="5" y="4" width="3" height="12" rx="1" fill="currentColor"/><rect x="12" y="4" width="3" height="12" rx="1" fill="currentColor"/></g>,
    upload:     <g>{p("M10 13 V3 M5 8 L10 3 L15 8")}{p("M3 15 V17 H17 V15")}</g>,
    download:   <g>{p("M10 3 V13 M5 8 L10 13 L15 8")}{p("M3 15 V17 H17 V15")}</g>,
    spark:      p("M2 13 L6 8 L9 11 L13 4 L18 9"),
    check:      p("M4 10 L8 14 L16 6"),
    close:      <g>{p("M5 5 L15 15")}{p("M15 5 L5 15")}</g>,
    doc:        <g>{p("M5 2 H12 L15 5 V18 H5 Z")}{p("M12 2 V5 H15")}</g>,
    folder:     p("M3 6 V16 H17 V8 H10 L8 6 H3 Z"),
    user:       <g><circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth={stroke} fill="none"/>{p("M4 17 C 4 13, 7 12, 10 12 C 13 12, 16 13, 16 17")}</g>,
    users:      <g><circle cx="7" cy="7" r="2.5" stroke="currentColor" strokeWidth={stroke} fill="none"/><circle cx="14" cy="8" r="2" stroke="currentColor" strokeWidth={stroke} fill="none"/>{p("M3 16 C 3 13, 5 12, 7 12 C 9 12, 11 13, 11 16 M11 14 C 11 12, 12.5 11, 14 11 C 15.5 11, 17 12, 17 14")}</g>,
    graph:      <g><circle cx="5" cy="6" r="1.6" fill="currentColor"/><circle cx="15" cy="6" r="1.6" fill="currentColor"/><circle cx="10" cy="14" r="1.6" fill="currentColor"/>{p("M5 6 L10 14 L15 6 M5 6 L15 6")}</g>,
    report:     <g>{p("M4 3 H14 L16 5 V17 H4 Z")}{p("M7 8 H13 M7 11 H13 M7 14 H11")}</g>,
    settings:   <g><circle cx="10" cy="10" r="2" stroke="currentColor" strokeWidth={stroke} fill="none"/>{p("M10 2 L10 4 M10 16 L10 18 M2 10 L4 10 M16 10 L18 10 M4 4 L5.5 5.5 M14.5 14.5 L16 16 M4 16 L5.5 14.5 M14.5 5.5 L16 4")}</g>,
    bell:       <g>{p("M5 14 V9 C5 6, 7 4, 10 4 C13 4, 15 6, 15 9 V14")}{p("M3 14 H17 M8 16 C8 17, 9 17.5, 10 17.5 C11 17.5, 12 17, 12 16")}</g>,
    home:       p("M3 9 L10 3 L17 9 V17 H12 V12 H8 V17 H3 Z"),
    branch:     <g><circle cx="5" cy="5" r="1.6" fill="currentColor"/><circle cx="5" cy="15" r="1.6" fill="currentColor"/><circle cx="15" cy="9" r="1.6" fill="currentColor"/>{p("M5 7 V13 M5 9 C 5 9, 8 9, 10 9 C 12 9, 13 9, 13 9")}</g>,
    grid:       <g>{p("M3 3 H8 V8 H3 Z M12 3 H17 V8 H12 Z M3 12 H8 V17 H3 Z M12 12 H17 V17 H12 Z")}</g>,
    list:       <g>{p("M5 5 H17 M5 10 H17 M5 15 H17")}<circle cx="3" cy="5" r="0.5" fill="currentColor"/><circle cx="3" cy="10" r="0.5" fill="currentColor"/><circle cx="3" cy="15" r="0.5" fill="currentColor"/></g>,
    arrow:      p("M3 10 H17 M12 5 L17 10 L12 15"),
    arrowL:     p("M17 10 H3 M8 5 L3 10 L8 15"),
    sparkle:    p("M10 2 L11.5 8 L17 9.5 L11.5 11 L10 17 L8.5 11 L3 9.5 L8.5 8 Z"),
    book:       <g>{p("M3 4 C 3 4, 6 3, 10 4 C 14 3, 17 4, 17 4 V16 C 17 16, 14 15, 10 16 C 6 15, 3 16, 3 16 Z")}{p("M10 4 V16")}</g>,
    bolt:       <path d="M11 2 L4 11 L9 11 L8 18 L15 9 L10 9 Z" stroke="currentColor" strokeWidth={stroke} strokeLinejoin="round" fill="none"/>,
    layers:     <g>{p("M10 3 L17 7 L10 11 L3 7 Z")}{p("M3 11 L10 15 L17 11")}{p("M3 14.5 L10 18.5 L17 14.5")}</g>,
    filter:     p("M3 5 H17 L12 11 V16 L8 14 V11 Z"),
    more:       <g><circle cx="5" cy="10" r="1.4" fill="currentColor"/><circle cx="10" cy="10" r="1.4" fill="currentColor"/><circle cx="15" cy="10" r="1.4" fill="currentColor"/></g>,
    sliders:    <g>{p("M3 6 H7 M11 6 H17 M3 14 H11 M15 14 H17")}<circle cx="9" cy="6" r="1.6" stroke="currentColor" strokeWidth={stroke} fill="white"/><circle cx="13" cy="14" r="1.6" stroke="currentColor" strokeWidth={stroke} fill="white"/></g>,
    eye:        <g>{p("M2 10 C 2 10, 5 5, 10 5 C 15 5, 18 10, 18 10 C 18 10, 15 15, 10 15 C 5 15, 2 10, 2 10 Z")}<circle cx="10" cy="10" r="2" stroke="currentColor" strokeWidth={stroke} fill="none"/></g>,
    star:       p("M10 2 L12.4 7.5 L18 8 L13.7 12 L15 18 L10 14.8 L5 18 L6.3 12 L2 8 L7.6 7.5 Z"),
    pin:        p("M10 2 V11 M10 11 L7 14 H13 L10 11 M10 14 V18"),
    lock:       <g>{p("M6 9 V6 C 6 4, 8 3, 10 3 C 12 3, 14 4, 14 6 V9")}{p("M4 9 H16 V17 H4 Z")}</g>,
    cloud:      p("M5 13 C 3 13, 2 11, 2 10 C 2 8, 4 7, 5 7 C 5 5, 7 3, 10 3 C 13 3, 14 6, 14 7 C 16 7, 18 8, 18 11 C 18 13, 16 14, 14 14 H 5 Z"),
    refresh:    <g>{p("M3 5 V9 H7")}{p("M3 9 C 4 5, 7 3, 10 3 C 14 3, 17 7, 17 10 M17 15 V11 H13")}{p("M17 11 C 16 15, 13 17, 10 17 C 6 17, 3 13, 3 10")}</g>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" style={{ display: "block", flex: "none" }}>
      {map[name] || null}
    </svg>
  );
}

// ─── 04 · Buttons ───────────────────────────────────────────
ABC.Buttons = () => (
  <div style={{ height: "100%", padding: 56, display: "flex", flexDirection: "column", gap: 32 }}>
    <div className="stack gap-2">
      <span className="t-section-head">Controls · 04</span>
      <h2 className="t-largeTitle" style={{ margin: 0 }}>Buttons & status</h2>
      <span className="t-body" style={{ color: "var(--text-secondary)" }}>Pill-shaped, generous tap targets. Filled · Tinted · Plain · Destructive.</span>
    </div>

    <div className="card card-pad-lg">
      <div className="t-section-head" style={{ marginBottom: 16 }}>Hierarchy</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 24 }}>
        {[
          { label: "Filled", btn: <button className="btn btn--primary btn--lg">Run simulation</button>, sub: "Primary action · max one per surface" },
          { label: "Tinted", btn: <button className="btn btn--tinted btn--lg">Open report</button>, sub: "Mid-emphasis action" },
          { label: "Plain", btn: <button className="btn btn--secondary btn--lg">Configure</button>, sub: "Neutral action · in toolbars" },
          { label: "Destructive", btn: <button className="btn btn--lg" style={{ background: "var(--status-red)", color: "#fff" }}>Delete run</button>, sub: "Confirms in dialog" },
        ].map((c) => (
          <div key={c.label} className="stack gap-3">
            <span className="t-section-head">{c.label}</span>
            {c.btn}
            <span className="t-footnote" style={{ color: "var(--text-secondary)" }}>{c.sub}</span>
          </div>
        ))}
      </div>
    </div>

    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28 }}>
      <div className="card card-pad-lg">
        <div className="t-section-head" style={{ marginBottom: 16 }}>Sizes</div>
        <div className="hstack gap-3" style={{ alignItems: "center" }}>
          <button className="btn btn--primary btn--lg">Large · 40</button>
          <button className="btn btn--primary">Medium · 32</button>
          <button className="btn btn--primary btn--sm">Small · 28</button>
        </div>
        <div className="t-section-head" style={{ marginTop: 24, marginBottom: 12 }}>With icon</div>
        <div className="hstack gap-3">
          <button className="btn btn--primary"><Icon name="play"/>Run</button>
          <button className="btn btn--tinted"><Icon name="upload"/>Upload</button>
          <button className="btn btn--secondary"><Icon name="download"/>Export</button>
          <button className="btn btn--secondary btn--icon"><Icon name="more"/></button>
        </div>
        <div className="t-section-head" style={{ marginTop: 24, marginBottom: 12 }}>Disabled</div>
        <div className="hstack gap-3">
          <button className="btn btn--primary" style={{ opacity: 0.4, pointerEvents: "none" }}>Run simulation</button>
          <button className="btn btn--secondary" style={{ opacity: 0.4 }}>Configure</button>
        </div>
      </div>

      <div className="card card-pad-lg">
        <div className="t-section-head" style={{ marginBottom: 16 }}>Segmented</div>
        <div className="stack gap-4">
          <div className="segmented">
            <div className="seg active">Personas</div>
            <div className="seg">Graph</div>
            <div className="seg">Discussion</div>
            <div className="seg">Report</div>
          </div>
          <div className="segmented" style={{ alignSelf: "flex-start" }}>
            <div className="seg"><Icon name="grid"/></div>
            <div className="seg active"><Icon name="list"/></div>
          </div>
        </div>

        <div className="t-section-head" style={{ marginTop: 28, marginBottom: 12 }}>Status pills</div>
        <div className="hstack" style={{ flexWrap: "wrap", gap: 8 }}>
          <span className="pill pill--green"><span className="dot"></span>Done</span>
          <span className="pill pill--blue"><span className="dot"></span>Running · Round 12</span>
          <span className="pill pill--orange"><span className="dot"></span>Retry 2/3</span>
          <span className="pill pill--red"><span className="dot"></span>Failed</span>
          <span className="pill pill--teal"><span className="dot"></span>Queued</span>
          <span className="pill pill--purple"><span className="dot"></span>Branch · ScenarioB</span>
          <span className="pill"><span className="dot"></span>Draft</span>
        </div>

        <div className="t-section-head" style={{ marginTop: 28, marginBottom: 12 }}>Confidence chips</div>
        <div className="hstack gap-2">
          {["High", "Medium", "Low"].map((c, i) => (
            <span key={c} className="pill" style={{
              background: i===0 ? "var(--status-green-bg)" : i===1 ? "var(--status-orange-bg)" : "var(--status-red-bg)",
              color:      i===0 ? "var(--status-green)"    : i===1 ? "var(--status-orange)"    : "var(--status-red)",
            }}>
              <Icon name="check" size={12}/>{c}
            </span>
          ))}
        </div>
      </div>
    </div>

    <div className="card card-pad-lg">
      <div className="t-section-head" style={{ marginBottom: 16 }}>In context · toolbar</div>
      <div className="hstack" style={{
        padding: "10px 12px",
        borderRadius: "var(--r-pill)",
        background: "var(--surface-inset)",
        gap: 6,
      }}>
        <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: "0" }}><Icon name="arrowL" size={14}/>Back</button>
        <span className="t-headline" style={{ marginLeft: 12 }}>EU AI Act Dossier · v3</span>
        <span className="pill pill--green" style={{ marginLeft: 8 }}><span className="dot"></span>Live</span>
        <div style={{ flex: 1 }}/>
        <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: "0" }}><Icon name="users" size={14}/>Personas</button>
        <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: "0" }}><Icon name="graph" size={14}/>Graph</button>
        <button className="btn btn--secondary btn--sm" style={{ background: "transparent", boxShadow: "none", border: "0" }}><Icon name="report" size={14}/>Report</button>
        <button className="btn btn--primary btn--sm"><Icon name="play" size={12}/>Run</button>
      </div>
    </div>
  </div>
);

// ─── 05 · Inputs · Toggles · Sliders ────────────────────────
ABC.Inputs = () => {
  const Field = ({ label, children, hint }) => (
    <div className="stack gap-2">
      <span className="t-subhead" style={{ color: "var(--text-secondary)" }}>{label}</span>
      {children}
      {hint && <span className="t-footnote" style={{ color: "var(--text-tertiary)" }}>{hint}</span>}
    </div>
  );

  return (
    <div style={{ height: "100%", padding: 56, display: "flex", flexDirection: "column", gap: 28 }}>
      <div className="stack gap-2">
        <span className="t-section-head">Controls · 05</span>
        <h2 className="t-largeTitle" style={{ margin: 0 }}>Forms & data input</h2>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 28 }}>
        <div className="card card-pad-lg">
          <div className="t-section-head" style={{ marginBottom: 16 }}>Text input</div>
          <div className="stack gap-5">
            <Field label="Project name">
              <div className="field">
                <input defaultValue="EU AI Act · Public Reaction" />
              </div>
            </Field>
            <Field label="Search" hint="Cmd K opens command palette">
              <div className="search">
                <Icon name="search" size={14}/>
                <span style={{ color: "var(--text-tertiary)" }}>Search personas, runs, evidence…</span>
              </div>
            </Field>
            <Field label="Description">
              <div className="field" style={{ height: "auto", padding: 12, alignItems: "flex-start" }}>
                <span style={{ color: "var(--text-tertiary)" }}>What public should Agora model? Add demographics, geographies, communities…</span>
              </div>
            </Field>
            <Field label="Focused (with ring)">
              <div className="field" style={{ borderColor: "var(--accent)", boxShadow: "0 0 0 3px var(--focus-ring)" }}>
                <input defaultValue="Brussels civic forum" />
              </div>
            </Field>
            <Field label="With error" hint={<span style={{ color: "var(--status-red)" }}>API key is invalid or expired.</span>}>
              <div className="field" style={{ borderColor: "var(--status-red)" }}>
                <input defaultValue="sk-••••••••••••••••" />
              </div>
            </Field>
          </div>
        </div>

        <div className="card card-pad-lg">
          <div className="t-section-head" style={{ marginBottom: 16 }}>Toggles · sliders · selects</div>
          <div className="stack gap-1" style={{ background: "var(--surface-inset)", borderRadius: 12, padding: 4 }}>
            {[
              ["Stream live updates", "Server-Sent Events", true, "blue"],
              ["Persona Review", "Manual approval before run", true, "blue"],
              ["Auto-branch on conflict", "Spawn scenarios when stance polarizes", false, "blue"],
              ["Local-only mode", "Disable cloud calls completely", false, "green"],
            ].map(([label, hint, on, kind]) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: 8, background: "white" }}>
                <div className="stack" style={{ flex: 1 }}>
                  <span className="t-callout" style={{ fontWeight: 500 }}>{label}</span>
                  <span className="t-footnote" style={{ color: "var(--text-secondary)" }}>{hint}</span>
                </div>
                <span className={`toggle ${on ? "on" : ""} ${kind==="blue" ? "on--blue" : ""}`}/>
              </div>
            ))}
          </div>

          <div className="stack gap-4" style={{ marginTop: 24 }}>
            <Field label="Rounds (8 selected)">
              <div className="hstack gap-3">
                <div style={{ flex: 1, height: 4, borderRadius: 2, background: "var(--gray-5)", position: "relative" }}>
                  <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "62%", background: "var(--accent)", borderRadius: 2 }}/>
                  <div style={{ position: "absolute", left: "62%", top: -8, width: 20, height: 20, borderRadius: 10, background: "white", boxShadow: "0 1px 3px rgba(0,0,0,0.12), 0 0 0 0.5px rgba(0,0,0,0.04)" }}/>
                </div>
                <span className="t-mono t-callout" style={{ minWidth: 32, textAlign: "right" }}>8</span>
              </div>
            </Field>
            <Field label="Temperature (0.7)">
              <div className="hstack gap-3">
                <div style={{ flex: 1, height: 4, borderRadius: 2, background: "var(--gray-5)", position: "relative" }}>
                  <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "70%", background: "var(--accent)", borderRadius: 2 }}/>
                  <div style={{ position: "absolute", left: "70%", top: -8, width: 20, height: 20, borderRadius: 10, background: "white", boxShadow: "0 1px 3px rgba(0,0,0,0.12), 0 0 0 0.5px rgba(0,0,0,0.04)" }}/>
                </div>
                <span className="t-mono t-callout" style={{ minWidth: 32, textAlign: "right" }}>0.7</span>
              </div>
            </Field>
            <Field label="LLM provider">
              <div className="field" style={{ justifyContent: "space-between" }}>
                <div className="hstack gap-2">
                  <span className="icon-chip icon-chip--blue" style={{ width: 22, height: 22, borderRadius: 6 }}><Icon name="sparkle" size={12}/></span>
                  <span>Claude Haiku 4.5</span>
                </div>
                <Icon name="chevronD" size={14}/>
              </div>
            </Field>
            <Field label="Output format">
              <div className="segmented" style={{ alignSelf: "flex-start" }}>
                <div className="seg active">PDF</div>
                <div className="seg">Markdown</div>
                <div className="seg">Notion</div>
                <div className="seg">JSON</div>
              </div>
            </Field>
          </div>
        </div>
      </div>

      <div className="card card-pad-lg">
        <div className="t-section-head" style={{ marginBottom: 16 }}>Grouped list · settings (Apple)</div>
        <div style={{ maxWidth: 720 }}>
          <div className="sec-head" style={{ paddingTop: 0 }}>General</div>
          <div className="group">
            <div className="row">
              <span className="icon-chip icon-chip--blue"><Icon name="cloud" size={14}/></span>
              <div className="row-label stack">
                <span className="t-callout" style={{ fontWeight: 500 }}>Cloud sync</span>
                <span className="t-footnote text-secondary">Encrypted · last sync 2 min ago</span>
              </div>
              <span className="toggle on on--blue"/>
            </div>
            <div className="row">
              <span className="icon-chip icon-chip--purple"><Icon name="lock" size={14}/></span>
              <div className="row-label stack">
                <span className="t-callout" style={{ fontWeight: 500 }}>Single sign-on</span>
                <span className="t-footnote text-secondary">SAML · Okta · acme.com</span>
              </div>
              <span className="t-footnote text-secondary">Connected</span>
              <Icon name="chevron" size={14}/>
            </div>
            <div className="row">
              <span className="icon-chip icon-chip--green"><Icon name="users" size={14}/></span>
              <div className="row-label stack">
                <span className="t-callout" style={{ fontWeight: 500 }}>Workspace members</span>
                <span className="t-footnote text-secondary">12 members · 3 roles</span>
              </div>
              <Icon name="chevron" size={14}/>
            </div>
          </div>
          <div className="t-footnote" style={{ color: "var(--text-tertiary)", padding: "8px 16px" }}>
            Cloud sync stores encrypted artefacts in your private bucket. Local-first mode disables uploads.
          </div>
        </div>
      </div>
    </div>
  );
};

window.ABC = ABC;
window.Icon = Icon;
