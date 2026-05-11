/* Agora Design System — App Screens B: Templates · Datasets · Project · Users · Run · Wizard */

const DSB = {};

// ─── 4) Templates / Builder ─────────────────────────────────
DSB.Templates = () => (
  <DSAppShell active="templates" crumbs={["Templates", "Builder"]}>
    <DSPageHeader title="Templates" subtitle="Prompts, Berichtsvorlagen und wiederverwendbare Workflows bauen."/>

    <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 20 }}>
      <DSCard title="Template-Kategorien">
        {[
          ["Stakeholder Simulation", 12, true],
          ["Report Generation", 8],
          ["Evaluation", 6],
          ["Ontology", 4],
          ["Persona Builder", 10],
          ["Custom", 3],
        ].map(([n, c, active], i) => (
          <div key={n} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 12px", marginTop: i ? 6 : 0,
            borderRadius: 8, fontSize: 14,
            background: active ? "var(--accent-tint-bg)" : "transparent",
            color: active ? "var(--accent)" : "var(--text-primary)",
            border: active ? "1px solid var(--accent-tint-bg-strong)" : "1px solid var(--hairline)",
            fontWeight: active ? 600 : 500,
          }}>
            <span>{n}</span>
            <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{c}</span>
          </div>
        ))}
      </DSCard>

      <DSCard title="Template Builder" subtitle="Variablen, Guardrails und Testlauf in einem Screen">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 160px auto", gap: 14, marginBottom: 18, alignItems: "end" }}>
          <DSField label="Name"><DSInput value="DACH Stakeholder Simulation"/></DSField>
          <DSField label="Version"><DSInput value="v1.8"/></DSField>
          <span className="pill pill--green" style={{ marginBottom: 8 }}><span className="dot"/>Published</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16 }}>
          <div style={{
            background: "#0c0f14", color: "#e1e8f5",
            fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.7,
            padding: 18, borderRadius: 12,
          }}>
            <div style={{ color: "#7dd3fc", fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", marginBottom: 10 }}>SYSTEM</div>
            <div>Du bist ein Simulationsagent für {`{{region}}`}.</div>
            <div>Analysiere nur Fakten aus dem Seed.</div>
            <div style={{ height: 10 }}/>
            <div>STAKEHOLDER:</div>
            <div>{`{{stakeholder_groups}}`}</div>
            <div style={{ height: 10 }}/>
            <div>ZIEL:</div>
            <div>- Reaktionen über {`{{time_horizon}}`} simulieren</div>
            <div>- Risiken mit Ursache, Signal, Gegenmaßnahme bewerten</div>
            <div>- Kein Bullshit-Bingo. Das schafft der Markt schon allein.</div>
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Variablen</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <DSField label="region"><DSInput value="DACH" mono/></DSField>
              <DSField label="time_horizon"><DSInput value="6 Monate" mono/></DSField>
              <DSField label="stakeholder_groups"><DSInput value="array" mono/></DSField>
              <DSField label="model_tier"><DSInput value="high_quality" mono/></DSField>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
              <button className="btn btn--primary">Testlauf</button>
              <button className="btn btn--secondary">Speichern</button>
            </div>
          </div>
        </div>
      </DSCard>
    </div>
  </DSAppShell>
);

// ─── 5) Datasets ─────────────────────────────────────────────
DSB.Datasets = () => (
  <DSAppShell active="datasets" crumbs={["Datasets"]}>
    <DSPageHeader title="Datasets" subtitle="Seed-Dokumente, Quellenqualität und Graph-Extraktion verwalten."/>

    <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 20 }}>
      <DSCard
        title="Dataset Library"
        subtitle="Dokumente, Uploads und Extraktionsstatus"
        right={<button className="btn btn--primary"><Icon name="plus" size={12}/>Dataset hochladen</button>}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
          <thead>
            <tr style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              <th style={{ textAlign: "left", padding: "8px 8px" }}>Name</th>
              <th style={{ textAlign: "left", padding: "8px 8px" }}>Typ</th>
              <th style={{ textAlign: "left", padding: "8px 8px" }}>Größe</th>
              <th style={{ textAlign: "left", padding: "8px 8px" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["seed_heinrich_soehne.md", "Markdown", "96 KB", "Synced", "green"],
              ["kundenfeedback_q1.csv", "CSV", "1.2 MB", "Synced", "green"],
              ["betriebsversammlung_notes.pdf", "PDF", "340 KB", "Running", "orange"],
              ["lieferantenliste.xlsx", "XLSX", "88 KB", "Draft", "purple"],
            ].map((r) => (
              <tr key={r[0]} style={{ borderTop: "1px solid var(--separator)" }}>
                <td style={{ padding: "12px 8px", fontFamily: "var(--font-mono)" }}>{r[0]}</td>
                <td style={{ padding: "12px 8px", color: "var(--text-secondary)" }}>{r[1]}</td>
                <td style={{ padding: "12px 8px", color: "var(--text-secondary)" }}>{r[2]}</td>
                <td style={{ padding: "12px 8px" }}><span className={`pill pill--${r[4]}`}><span className="dot"/>{r[3]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </DSCard>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <DSCard title="Extraktionsvorschau" subtitle="Was aus dem Seed wirklich im Graph landet">
          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 8 }}>Erkannte Entitäten</div>
          {[
            ["Stakeholder", 5, "blue"],
            ["Risiken", 17, "orange"],
            ["Termine", 8, "teal"],
            ["Abhängigkeiten", 31, "green"],
          ].map(([k,v,c]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderTop: "1px solid var(--separator)" }}>
              <span style={{ fontSize: 14 }}>{k}</span>
              <span className={`pill pill--${c}`}>{v}</span>
            </div>
          ))}
          <div style={{ marginTop: 14, padding: 12, background: "var(--surface-canvas)", borderRadius: 8, fontSize: 12.5, color: "var(--text-secondary)" }}>
            Hinweis: 3 Passagen sind semantisch dünn. Menschen nennen das dann „Input".
          </div>
        </DSCard>

        <DSCard title="Upload Drawer" subtitle="Quelle hinzufügen und direkt zur Pipeline schicken">
          <div style={{
            border: "2px dashed var(--hairline-strong)", borderRadius: 12,
            padding: 24, textAlign: "center", background: "var(--surface-canvas)",
          }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>Datei hier ablegen</div>
            <div style={{ fontSize: 12.5, color: "var(--text-tertiary)", marginTop: 4 }}>PDF, MD, CSV, TXT, DOCX, XLSX</div>
          </div>
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 6, fontWeight: 500 }}>Parsing-Modus</div>
            <div className="segmented">
              <div className="seg">Schnell</div>
              <div className="seg active">Genau</div>
              <div className="seg">OCR erzwingen</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn btn--primary">Import starten</button>
            <button className="btn btn--secondary">Cancel</button>
          </div>
        </DSCard>
      </div>
    </div>
  </DSAppShell>
);

// ─── 6) Project Detail ──────────────────────────────────────
DSB.Project = () => (
  <DSAppShell active="projects" crumbs={["Projects", "Heinrich Söhne GmbH"]}>
    <DSPageHeader title="Projekt: Heinrich Söhne GmbH"
      subtitle="Projekt-Dashboard mit eigenem Untermenü für Seed Docs, Graph, Runs und Settings."/>

    <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 20 }}>
      <DSCard title="Projektmenü">
        {["Overview","Seed Documents","Knowledge Graph","Personas","Runs","Reports","Settings"].map((m, i) => (
          <div key={m} style={{
            padding: "9px 12px", marginTop: i ? 4 : 0, borderRadius: 8, fontSize: 14,
            background: i===0 ? "var(--accent-tint-bg)" : "transparent",
            color: i===0 ? "var(--accent)" : "var(--text-primary)",
            fontWeight: i===0 ? 600 : 500,
          }}>{m}</div>
        ))}
        <div style={{ marginTop: 16 }}>
          <button className="btn btn--primary" style={{ width: "100%" }}><Icon name="plus" size={12}/>Neuer Run</button>
        </div>
      </DSCard>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <DSCard pad={22}>
          <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.012em" }}>4-Tage-Woche bei vollem Lohnausgleich</div>
          <div style={{ fontSize: 14, color: "var(--text-secondary)", marginTop: 6 }}>
            Zeithorizont Jan–Jun 2026 · 5 Stakeholder-Gruppen · Fokus: Betriebsversammlung, Vertrieb Freitag, Margendruck
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <span className="pill pill--green"><span className="dot"/>Status: aktiv</span>
            <span className="pill pill--purple">Graph: 4.591 Nodes</span>
            <span className="pill pill--orange">Letzter Run: 06:42</span>
          </div>
        </DSCard>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <DSCard title="Seed-Qualität" subtitle="Struktur, Faktenlage und Lücken">
            <div style={{ fontSize: 36, fontWeight: 700, letterSpacing: "-0.022em", fontVariantNumeric: "tabular-nums" }}>82 <span style={{ fontSize: 18, color: "var(--text-tertiary)", fontWeight: 500 }}>/ 100</span></div>
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              {[["Fakten",78],["Stakeholder-Abdeckung",82],["Risiken",92]].map(([k,v]) => (
                <div key={k}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, color: "var(--text-secondary)" }}>
                    <span>{k}</span><span className="t-mono">{v}%</span>
                  </div>
                  <div className="bar" style={{ marginTop: 4 }}><i style={{ width: `${v}%` }}/></div>
                </div>
              ))}
            </div>
          </DSCard>
          <DSCard title="Knowledge Graph" subtitle="Ausschnitt des Projektgraphen">
            <svg viewBox="0 0 320 180" style={{ width: "100%", height: 200 }}>
              <line x1="80" y1="60" x2="160" y2="40" stroke="var(--hairline-strong)"/>
              <line x1="160" y1="40" x2="240" y2="70" stroke="var(--hairline-strong)"/>
              <line x1="80" y1="60" x2="120" y2="130" stroke="var(--hairline-strong)"/>
              <line x1="160" y1="40" x2="240" y2="120" stroke="var(--hairline-strong)"/>
              <line x1="120" y1="130" x2="240" y2="120" stroke="var(--hairline-strong)"/>
              {[
                [80,60,"Belegschaft","blue"],
                [160,40,"Vertrieb","green"],
                [240,70,"Marge","red"],
                [120,130,"Freitag","orange"],
                [240,120,"Kunden","purple"],
              ].map(([x,y,l,c]) => (
                <g key={l}>
                  <rect x={x-44} y={y-12} width="88" height="24" rx="12" fill={`var(--status-${c==="blue"?"":""}${c==="blue"?"":""})`} style={{
                    fill: c==="blue" ? "var(--accent-tint-bg)" : `var(--status-${c}-bg)`,
                  }}/>
                  <text x={x} y={y+4} textAnchor="middle" fontSize="11" fontWeight="600"
                    style={{ fill: c==="blue" ? "var(--accent-tint-text)" : `var(--status-${c})` }}>{l}</text>
                </g>
              ))}
            </svg>
          </DSCard>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <DSCard title="Letzte Reports" subtitle="Drafts und Exporte">
            {[
              ["Management Summary","Heute 06:58","Draft","purple"],
              ["Risikoanalyse Betriebsversammlung","Gestern","Live","green"],
              ["Kundenreaktion Freitag","Mo","Live","green"],
            ].map(([r,t,s,c], i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 90px 80px", gap: 12, padding: "10px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
                <span style={{ fontSize: 13.5, fontWeight: 500 }}>{r}</span>
                <span style={{ fontSize: 12.5, color: "var(--text-tertiary)" }}>{t}</span>
                <span className={`pill pill--${c}`}><span className="dot"/>{s}</span>
              </div>
            ))}
          </DSCard>
          <DSCard title="Run-Historie" subtitle="Vergleich der wichtigsten Runs">
            {[
              ["v7-gpt55","94%","8,74 €","Running","orange"],
              ["v6-kimi","87%","0 €","Completed","green"],
              ["v5-deepseek","81%","0 €","Completed","green"],
            ].map(([r,q,c,s,col], i) => (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 50px 60px 90px", gap: 12, padding: "10px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
                <span style={{ fontSize: 13.5, fontFamily: "var(--font-mono)" }}>{r}</span>
                <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{q}</span>
                <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{c}</span>
                <span className={`pill pill--${col}`}><span className="dot"/>{s}</span>
              </div>
            ))}
          </DSCard>
        </div>
      </div>
    </div>
  </DSAppShell>
);

// ─── 7) Users & Teams ───────────────────────────────────────
DSB.Users = () => (
  <DSAppShell active="settings" openGroup="settings" subActive="users-teams"
    crumbs={["Settings", "Users & Teams"]}>
    <DSPageHeader title="Users & Teams" subtitle="Rollen, Rechte und Team-Zugriff auf Projekte und Provider."/>

    <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 20 }}>
      <DSCard title="Benutzer" right={<button className="btn btn--primary"><Icon name="plus" size={12}/>Invite</button>}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
          <thead>
            <tr style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              {["User","Role","Scope","Status"].map((h) => <th key={h} style={{ textAlign: "left", padding: "8px 8px" }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {[
              ["Alex Developer","Owner","All projects","Active","green"],
              ["BFW Reviewer","Reviewer","Reports only","Active","green"],
              ["Automation Bot","Service Account","Runs + datasets","Active","green"],
              ["Guest Demo","Viewer","Demo project","Pending","orange"],
            ].map((r) => (
              <tr key={r[0]} style={{ borderTop: "1px solid var(--separator)" }}>
                <td style={{ padding: "12px 8px", fontWeight: 500 }}>{r[0]}</td>
                <td style={{ padding: "12px 8px", color: "var(--text-secondary)" }}>{r[1]}</td>
                <td style={{ padding: "12px 8px", color: "var(--text-secondary)" }}>{r[2]}</td>
                <td style={{ padding: "12px 8px" }}><span className={`pill pill--${r[4]}`}><span className="dot"/>{r[3]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </DSCard>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <DSCard title="RBAC Matrix" subtitle={'Minimalrechte statt „admin für alle“, weil Chaos keine Architektur ist.'}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 10, fontSize: 13 }}>
            <div style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Role</div>
            <div style={{ color: "var(--text-secondary)", fontSize: 11.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Permission</div>
            {[
              ["Owner","all:write"],
              ["Admin","settings:write"],
              ["Operator","runs:write"],
              ["Reviewer","reports:read"],
              ["Viewer","projects:read"],
            ].flatMap(([r,p]) => [
              <div key={r+"r"} style={{ padding: "10px 0", borderTop: "1px solid var(--separator)", fontWeight: 500 }}>{r}</div>,
              <div key={r+"p"} style={{ padding: "10px 0", borderTop: "1px solid var(--separator)", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>{p}</div>,
            ])}
          </div>
        </DSCard>
        <DSCard title="Audit Preview" subtitle="Letzte Rechte-Änderungen">
          {[
            ["06:45","Automation Bot","created run"],
            ["06:12","Alex","changed routing"],
            ["Gestern","Reviewer","exported report"],
            ["Mo","Guest Demo","login failed"],
          ].map(([t,u,a], i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "70px 1fr", gap: 12, padding: "10px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{t}</span>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>{u}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{a}</div>
              </div>
            </div>
          ))}
        </DSCard>
      </div>
    </div>
  </DSAppShell>
);

// ─── 8) Run Detail ──────────────────────────────────────────
DSB.RunDetail = () => {
  const stages = [
    ["document_ingest","Dataset einlesen","qwen3-coder-next:cloud","Completed","green"],
    ["ontology_generation","Ontologie erzeugen","gemini-3-flash","Completed","green"],
    ["graph_build","Graph bauen","gpt-5.5-mini","Completed","green"],
    ["persona_generation","Personas generieren","gemini-3-pro","Completed","green"],
    ["simulation_rounds","Simulation laufen lassen","gpt-5.5","Running","orange"],
    ["report_generation","Bericht erzeugen","gpt-5.5","Pending","gray"],
    ["evaluation","Qualität bewerten","deepseek-v4-flash:cloud","Pending","gray"],
  ];
  return (
    <DSAppShell active="runs" crumbs={["Runs", "Run Detail"]}>
      <DSPageHeader title="Run Detail" subtitle="Pipeline, Logs, Artefakte und Kosten eines Simulationslaufs."
        right={<div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="pill pill--orange"><span className="dot"/>Running</span>
          <button className="btn btn--primary"><Icon name="pause" size={12}/>Pause</button>
        </div>}/>

      <DSCard pad={18}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.005em" }}>run_2026-05-11_0642 · Heinrich Söhne GmbH · 4-Tage-Woche</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
              72 Runden · 5 Stakeholder-Gruppen · Snapshot v7 · Seed: <span style={{ fontFamily: "var(--font-mono)" }}>seed_heinrich_soehne.md</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <span className="pill pill--blue">Cost 8,74 €</span>
            <span className="pill">ETA 12 min</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 18 }}>
          {["Overview","Pipeline","Logs","Artifacts","Evaluation"].map((t, i) => (
            <span key={t} style={{
              padding: "7px 14px", borderRadius: 8, fontSize: 14, fontWeight: i===1 ? 600 : 500,
              color: i===1 ? "var(--accent)" : "var(--text-secondary)",
              border: i===1 ? "1px solid var(--accent-tint-bg-strong)" : "1px solid transparent",
              background: i===1 ? "var(--accent-tint-bg)" : "transparent",
            }}>{t}</span>
          ))}
        </div>
      </DSCard>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20, marginTop: 20 }}>
        <DSCard title="Stage Timeline" subtitle="Ein Stage nach dem anderen. Revolutionär, ich weiß.">
          <div style={{ position: "relative" }}>
            <div style={{ position: "absolute", left: 13, top: 14, bottom: 14, width: 2, background: "var(--separator)" }}/>
            {stages.map(([k, sub, m, s, c], i) => (
              <div key={k} style={{ display: "grid", gridTemplateColumns: "32px 1fr 200px 130px", gap: 14, padding: "12px 0", alignItems: "center", position: "relative" }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%",
                  background: s==="Completed" ? "var(--status-green-bg)" : s==="Running" ? "var(--status-orange-bg)" : "#fff",
                  border: s==="Pending" ? "1.5px solid var(--hairline-strong)" : "0",
                  color: s==="Completed" ? "var(--status-green)" : s==="Running" ? "var(--status-orange)" : "var(--text-tertiary)",
                  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1,
                }}>
                  {s==="Completed" ? <Icon name="check" size={14}/> : s==="Running" ? <Icon name="refresh" size={14}/> : <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--text-quaternary)" }}/>}
                </div>
                <div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 600 }}>{k}</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{sub}</div>
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--text-secondary)" }}>{m}</div>
                <span className={`pill pill--${c}`}><span className="dot"/>{s}</span>
              </div>
            ))}
          </div>
        </DSCard>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <DSCard title="Live Logs" subtitle="Nur die wichtigen Zeilen, nicht die gesamte digitale Müllhalde.">
            {[
              ["INFO","blue","round=44 stakeholder=customers tokens=8192"],
              ["WARN","orange","Friday availability concern increased"],
              ["INFO","blue","consensus edge created: suppliers→sales"],
              ["INFO","blue","stream chunk received after 149.2s"],
            ].map(([k,c,t], i) => (
              <div key={i} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
                <span className={`pill pill--${c}`} style={{ minWidth: 50, justifyContent: "center" }}>{k}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12.5 }}>{t}</span>
              </div>
            ))}
          </DSCard>
          <DSCard title="Artefakte" subtitle="Erzeugte Dateien dieses Runs">
            {[
              ["ontology.json","18 KB"],
              ["graph.cypher","440 KB"],
              ["personas.json","95 KB"],
              ["draft_report.md","pending"],
            ].map(([f,s], i) => (
              <div key={f} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <Icon name="doc" size={16}/>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>{f}</span>
                </div>
                <span style={{ fontSize: 12.5, color: s==="pending" ? "var(--text-tertiary)" : "var(--text-secondary)" }}>{s}</span>
              </div>
            ))}
          </DSCard>
        </div>
      </div>
    </DSAppShell>
  );
};

// ─── 9) New Run Wizard ──────────────────────────────────────
DSB.Wizard = () => {
  const Step = ({ n, label, state }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
      <span style={{
        width: 30, height: 30, borderRadius: "50%",
        background: state==="active" ? "var(--accent)" : state==="done" ? "var(--accent-tint-bg)" : "#fff",
        color: state==="active" ? "#fff" : state==="done" ? "var(--accent)" : "var(--text-tertiary)",
        border: state==="todo" ? "1.5px solid var(--hairline-strong)" : "0",
        fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flex: "none",
      }}>{n}</span>
      <span style={{ fontSize: 14, fontWeight: state==="active" ? 600 : 500,
        color: state==="active" ? "var(--accent)" : state==="done" ? "var(--text-primary)" : "var(--text-tertiary)" }}>{label}</span>
      {n < 5 && <div style={{ flex: 1, height: 1, background: "var(--hairline)" }}/>}
    </div>
  );

  return (
    <DSAppShell active="runs" crumbs={["Runs", "New Run Wizard"]}>
      <DSPageHeader title="Neuer Run" subtitle="Wizard für Projekt, Dataset, Routing-Snapshot und Output."/>

      <DSCard pad={20} style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Step n={1} label="Projekt" state="done"/>
          <Step n={2} label="Dataset" state="done"/>
          <Step n={3} label="Routing" state="active"/>
          <Step n={4} label="Simulation" state="todo"/>
          <Step n={5} label="Review" state="todo"/>
        </div>
      </DSCard>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <DSCard title="Routing wählen" subtitle="Stage-Routing kann für diesen Run überschrieben werden">
          {[
            ["Qualität maximal","OpenAI + Gemini Pro","Empfohlen für finale Reports","high","blue", true],
            ["Schnell & günstig","Ollama Cloud Mix","Für Vorabtests","fast","gray"],
            ["Lokal-first","Local Ollama + cached","Keine Cloud-Calls","local","gray"],
          ].map(([t, sub, hint, tag, c, active], i) => (
            <div key={i} style={{
              padding: 16, marginTop: i ? 10 : 0, borderRadius: 12,
              border: active ? "1.5px solid var(--accent)" : "1px solid var(--hairline)",
              background: active ? "var(--accent-tint-bg)" : "#fff",
              display: "flex", justifyContent: "space-between", alignItems: "flex-start",
            }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: active ? "var(--accent)" : "var(--text-primary)" }}>{t}</div>
                <div style={{ fontSize: 13, marginTop: 4 }}>{sub}</div>
                <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 4 }}>{hint}</div>
              </div>
              <span className={`pill pill--${c}`}>{tag}</span>
            </div>
          ))}
        </DSCard>

        <DSCard title="Preview" subtitle="Konfiguration vor Start">
          {[
            ["Projekt","Heinrich Söhne GmbH"],
            ["Dataset","seed_heinrich_soehne.md", true],
            ["Routing Snapshot","v8 draft → lock on start", true],
            ["Stages","7"],
            ["Runden","72"],
            ["Output","Report + Evaluation + Graph Diff"],
          ].map(([k,v,mono], i) => (
            <div key={k} style={{ display: "grid", gridTemplateColumns: "150px 1fr", gap: 12, padding: "12px 0", borderTop: i ? "1px solid var(--separator)" : "0", alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{k}</span>
              <span style={{ fontSize: 13.5, fontWeight: 500, fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)" }}>{v}</span>
            </div>
          ))}
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }}>
            <button className="btn btn--secondary">Zurück</button>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn--secondary">Als Draft</button>
              <button className="btn btn--primary">Run starten</button>
            </div>
          </div>
        </DSCard>
      </div>
    </DSAppShell>
  );
};

window.DSB = DSB;
