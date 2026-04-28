/* Pipeline screens: Personas table, Graph w/ legend, Skeleton/Progress states */

const ABPipeline = {};

ABPipeline.Personas = () => (
  <div className="ab ab-pad">
    <div className="ab-head">
      <div className="num">09</div>
      <div className="meta-stack">
        <div className="t-kicker t-kicker--accent">SCREEN · STEP 02 · ENVIRONMENT SETUP</div>
        <div className="title">Persona-Tabelle</div>
        <div className="coord-row">214 PERSONAS · 14 CLUSTER · DACH-ZEITPROFIL</div>
      </div>
    </div>
    <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
      <div className="row" style={{ gap: 10 }}>
        <div className="input-group" style={{ width: 280 }}>
          <span className="pfx">Q</span>
          <input className="input" placeholder="Personas durchsuchen …" />
        </div>
        <div className="segmented">
          <button className="seg is-active">Alle · 214</button>
          <button className="seg">Bridges · 3</button>
          <button className="seg">Skeptisch · 47</button>
          <button className="seg">Manuell · 4</button>
        </div>
      </div>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn btn--ghost btn--sm">Exportieren</button>
        <button className="btn btn--secondary btn--sm">+ Manuell</button>
        <button className="btn btn--primary btn--sm">Simulation vorbereiten <span className="arrow">→</span></button>
      </div>
    </div>
    <div className="panel">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 40 }}><span className="checkbox"></span></th>
            <th>№<span className="sort">↑</span></th>
            <th>Persona</th>
            <th>Rolle</th>
            <th>Cluster</th>
            <th>Haltung</th>
            <th className="col-num">Aktivität</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {[
            ["047", "Markus Renner", "Tech-Skeptiker", "#03", "skeptisch", "4 / Tag", "running"],
            ["112", "Lina Voß", "Aktivistin", "#01", "befürwortend", "9 / Tag", "running"],
            ["009", "Tomás Aldea", "Journalist", "#02", "neutral", "6 / Tag", "running"],
            ["158", "Petra Kühn", "Beamtin EU", "#03", "neutral", "2 / Tag", "queued"],
            ["203", "Yusuf Demir", "Unternehmer", "#04", "skeptisch", "3 / Tag", "running"],
            ["066", "Anja Walter", "Wissenschaftlerin", "#01", "befürwortend", "5 / Tag", "running"],
          ].map((r, i) => (
            <tr key={r[0]} className={i === 0 ? "is-selected" : ""}>
              <td><span className={"checkbox " + (i === 0 ? "is-checked" : "")}>{i === 0 ? "✓" : ""}</span></td>
              <td className="col-mono">{r[0]}</td>
              <td>
                <div className="row" style={{ gap: 10 }}>
                  <span style={{ width: 28, height: 28, border: "1px solid var(--rule-strong)", background: "var(--bg-sunken)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--ff-serif)", fontSize: 14 }}>{r[1][0]}</span>
                  <span style={{ color: "var(--fg)" }}>{r[1]}</span>
                </div>
              </td>
              <td style={{ color: "var(--fg-body)" }}>{r[2]}</td>
              <td><span className="tag">{r[3]}</span></td>
              <td>
                {r[4] === "skeptisch" && <span className="badge badge--warn">{r[4]}</span>}
                {r[4] === "befürwortend" && <span className="badge badge--success">{r[4]}</span>}
                {r[4] === "neutral" && <span className="badge badge--ghost">{r[4]}</span>}
              </td>
              <td className="col-num" style={{ color: "var(--fg)" }}>{r[5]}</td>
              <td>
                <span className="meta-mono" style={{ color: r[6] === "running" ? "var(--accent)" : "var(--plasma-400)" }}>
                  <span className={"status-dot status-dot--" + (r[6] === "running" ? "running" : "queued")} style={{ marginRight: 6 }}></span>
                  {r[6].toUpperCase()}
                </span>
              </td>
              <td><span className="meta-mono">···</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="panel-foot">
        <span className="meta-mono">1 AUSGEWÄHLT · 214 GESAMT</span>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn btn--ghost btn--sm">‹</button>
          <span className="meta-mono">1 / 36</span>
          <button className="btn btn--ghost btn--sm">›</button>
        </div>
      </div>
    </div>
  </div>
);

ABPipeline.GraphAndStates = () => (
  <div className="ab ab-pad">
    <div className="ab-head">
      <div className="num">10</div>
      <div className="meta-stack">
        <div className="t-kicker t-kicker--accent">GRAPH · LADE-ZUSTÄNDE · LEGENDE</div>
        <div className="title">Visualisierung & Loading</div>
        <div className="coord-row">CARTOGRAPHIC · KNOTEN-TYPEN · KANTEN-GEWICHT</div>
      </div>
    </div>
    <div className="grid-2" style={{ gap: 32 }}>
      <div className="panel">
        <div className="panel-head">
          <div className="title-line">
            <span className="t-kicker">GRAPH · ROUND 13</span>
          </div>
          <span className="meta-mono">SCALE 1:1</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div className="graph-canvas" style={{ height: 360 }}>
            <svg viewBox="0 0 600 360" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
              {/* Edges */}
              <line x1="80" y1="60" x2="280" y2="160" stroke="var(--rule-strong)" strokeWidth="1.5" />
              <line x1="280" y1="160" x2="500" y2="80" stroke="var(--rule-strong)" strokeWidth="1.5" />
              <line x1="280" y1="160" x2="180" y2="280" stroke="var(--plasma-400)" strokeWidth="2" />
              <line x1="280" y1="160" x2="420" y2="280" stroke="var(--rule)" strokeWidth="1" />
              <line x1="80" y1="60" x2="180" y2="280" stroke="var(--rule)" strokeWidth="1" />
              <line x1="500" y1="80" x2="420" y2="280" stroke="var(--rule)" strokeWidth="1" />
              <line x1="280" y1="160" x2="540" y2="220" stroke="var(--accent)" strokeWidth="2" />
              <line x1="180" y1="280" x2="420" y2="280" stroke="var(--rule)" strokeWidth="1" strokeDasharray="3 3" />
              {/* Nodes */}
              <circle cx="80" cy="60" r="8" fill="var(--mono-50)" />
              <circle cx="500" cy="80" r="8" fill="var(--mono-50)" />
              <circle cx="180" cy="280" r="7" fill="var(--plasma-400)" />
              <circle cx="180" cy="280" r="11" fill="none" stroke="var(--plasma-400)" strokeWidth="0.6" opacity="0.5" />
              <circle cx="420" cy="280" r="6" fill="var(--mono-300)" />
              <circle cx="280" cy="160" r="12" fill="var(--accent)" />
              <circle cx="280" cy="160" r="18" fill="none" stroke="var(--accent)" strokeWidth="0.6" opacity="0.4" />
              <circle cx="540" cy="220" r="6" fill="var(--accent)" />
              <text x="296" y="156" fontFamily="Geist Mono" fontSize="11" fill="var(--accent)" letterSpacing="1">EU-AI-ACT</text>
              <text x="92" y="58" fontFamily="Geist Mono" fontSize="10" fill="var(--mono-400)">KOMMISSION</text>
              <text x="510" y="78" fontFamily="Geist Mono" fontSize="10" fill="var(--mono-400)">PARLAMENT</text>
              <text x="190" y="296" fontFamily="Geist Mono" fontSize="10" fill="var(--plasma-400)">MARKUS · 47</text>
              <text x="430" y="296" fontFamily="Geist Mono" fontSize="10" fill="var(--mono-400)">LINA · 112</text>
            </svg>
          </div>
        </div>
        <div className="panel-foot">
          <div className="meta-mono">SCRUB · ROUND</div>
          <div className="slider-track" style={{ flex: 1, margin: "10px 16px" }}>
            <span className="fill" style={{ width: "54%" }}></span>
            <span className="thumb" style={{ left: "54%" }}></span>
          </div>
          <div className="meta-mono" style={{ color: "var(--accent)" }}>13 / 24</div>
        </div>
      </div>

      <div className="col" style={{ gap: 20 }}>
        <div className="panel">
          <div className="panel-head"><span className="t-kicker">LEGENDE</span></div>
          <div className="panel-body">
            <div className="col" style={{ gap: 14 }}>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--mono-50)" }}></span><span className="t-body-sm" style={{ color: "var(--fg)" }}>Entität</span><span className="meta-mono" style={{ marginLeft: "auto" }}>147</span></div>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--accent)", boxShadow: "var(--glow-accent)" }}></span><span className="t-body-sm" style={{ color: "var(--fg)" }}>Fokus</span><span className="meta-mono" style={{ marginLeft: "auto" }}>1</span></div>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--plasma-400)" }}></span><span className="t-body-sm" style={{ color: "var(--fg)" }}>Selektion</span><span className="meta-mono" style={{ marginLeft: "auto" }}>12</span></div>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 14, height: 14, borderRadius: "50%", background: "var(--mono-300)" }}></span><span className="t-body-sm" style={{ color: "var(--fg)" }}>Persona</span><span className="meta-mono" style={{ marginLeft: "auto" }}>214</span></div>
              <hr className="hairline" />
              <div className="meta-mono">KANTEN</div>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 24, height: 1, background: "var(--rule-strong)" }}></span><span className="t-body-sm">Relation</span></div>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 24, height: 2, background: "var(--accent)" }}></span><span className="t-body-sm">Verstärkt</span></div>
              <div className="row" style={{ gap: 12 }}><span style={{ width: 24, height: 1, background: "var(--rule)", borderTop: "1px dashed var(--mono-500)" }}></span><span className="t-body-sm">Schwach / temporal</span></div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><span className="t-kicker">SKELETON · LADE-ZUSTAND</span></div>
          <div className="panel-body">
            <div className="row" style={{ gap: 14, marginBottom: 14 }}>
              <span className="skel" style={{ width: 44, height: 44 }}></span>
              <div className="col" style={{ gap: 6, flex: 1 }}>
                <span className="skel" style={{ height: 12, width: "60%" }}></span>
                <span className="skel" style={{ height: 10, width: "40%" }}></span>
              </div>
            </div>
            <div className="col" style={{ gap: 6 }}>
              <span className="skel" style={{ height: 10 }}></span>
              <span className="skel" style={{ height: 10, width: "85%" }}></span>
              <span className="skel" style={{ height: 10, width: "70%" }}></span>
            </div>
            <hr className="hairline" style={{ margin: "16px 0" }} />
            <div className="meta-mono" style={{ marginBottom: 6 }}>PROGRESS · DETERMINIERT</div>
            <div className="progress"><div className="bar" style={{ width: "62%" }}></div></div>
            <div className="meta-mono" style={{ marginTop: 14, marginBottom: 6 }}>PROGRESS · INDETERMINIERT</div>
            <div className="progress progress--indeterminate"><div className="bar"></div></div>
          </div>
        </div>
      </div>
    </div>
  </div>
);

window.ABPipeline = ABPipeline;
