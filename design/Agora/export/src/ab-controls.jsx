/* Controls artboards: buttons, badges, inputs, switches, sliders, tabs */

const ABControls = {};

ABControls.Buttons = () => (
  <div className="ab ab-pad">
    <div className="ab-head">
      <div className="num">04</div>
      <div className="meta-stack">
        <div className="t-kicker t-kicker--accent">BUTTONS · FLATS, ZWEI HÖHEN, EIN AKZENT</div>
        <div className="title">Buttons & Toggles</div>
        <div className="coord-row">RADIUS 2PX · WHITE-BORDER ON HOVER · LOADING + ICON-VARIANT</div>
      </div>
    </div>
    <div className="grid-2" style={{ gap: 56 }}>
      <div className="group">
        <div className="group-label">Hierarchie</div>
        <div className="row">
          <button className="btn btn--primary">Simulation starten <span className="arrow">→</span></button>
          <button className="btn btn--secondary">Vorbereiten</button>
          <button className="btn btn--ghost">Abbrechen</button>
          <button className="btn btn--danger">Verwerfen</button>
        </div>
        <div className="row">
          <button className="btn btn--accent">Live ausführen <span className="dot-glow"></span></button>
          <button className="btn btn--plasma">Snapshot öffnen</button>
        </div>

        <div className="group-label" style={{ marginTop: 24 }}>Größen</div>
        <div className="row">
          <button className="btn btn--primary btn--lg">Persona generieren</button>
          <button className="btn btn--secondary">Vorbereiten</button>
          <button className="btn btn--ghost btn--sm">Mehr</button>
        </div>

        <div className="group-label" style={{ marginTop: 24 }}>Zustände</div>
        <div className="row">
          <button className="btn btn--primary" disabled>Bereit</button>
          <button className="btn btn--secondary">
            <span className="skel" style={{ width: 12, height: 12, borderRadius: "50%" }}></span>
            Lädt …
          </button>
          <button className="btn btn--ghost">
            <span className="status-dot status-dot--running"></span>
            Läuft · 04:12
          </button>
        </div>
      </div>

      <div className="group">
        <div className="group-label">Icon + Split</div>
        <div className="row">
          <button className="btn btn--icon btn--secondary" aria-label="Settings"><span className="glyph">⊟</span></button>
          <button className="btn btn--icon btn--ghost" aria-label="More"><span className="glyph">···</span></button>
          <button className="btn btn--icon btn--accent" aria-label="Run"><span className="glyph">▶</span></button>
        </div>
        <div className="row">
          <div className="btn-split">
            <button className="btn btn--secondary">Run · qwen3-coder</button>
            <button className="btn btn--secondary btn--icon" aria-label="Modell wählen"><span className="glyph">▾</span></button>
          </div>
        </div>

        <div className="group-label" style={{ marginTop: 24 }}>Switch · Checkbox · Radio</div>
        <div className="row" style={{ gap: 32 }}>
          <span className="row" style={{ gap: 10 }}>
            <span className="switch is-on" role="switch"></span>
            <span className="t-meta" style={{ color: "var(--fg)" }}>Live-Stream aktiv</span>
          </span>
          <span className="row" style={{ gap: 10 }}>
            <span className="switch" role="switch"></span>
            <span className="t-meta">Webtools</span>
          </span>
        </div>
        <div className="row" style={{ gap: 32 }}>
          <span className="row" style={{ gap: 10 }}>
            <span className="checkbox is-checked">✓</span>
            <span className="t-meta" style={{ color: "var(--fg)" }}>Personas speichern</span>
          </span>
          <span className="row" style={{ gap: 10 }}>
            <span className="checkbox"></span>
            <span className="t-meta">Tool-Use erlauben</span>
          </span>
          <span className="row" style={{ gap: 10 }}>
            <span className="radio is-checked"></span>
            <span className="t-meta" style={{ color: "var(--fg)" }}>Lokal</span>
          </span>
          <span className="row" style={{ gap: 10 }}>
            <span className="radio"></span>
            <span className="t-meta">Cloud</span>
          </span>
        </div>

        <div className="group-label" style={{ marginTop: 24 }}>Badges</div>
        <div className="row">
          <span className="badge badge--accent"><span className="dot"></span>LIVE</span>
          <span className="badge badge--plasma"><span className="dot"></span>SELECTED · 12</span>
          <span className="badge badge--success">DONE · 04:12</span>
          <span className="badge badge--warn">RETRY × 2</span>
          <span className="badge badge--error">500</span>
          <span className="badge">QUEUED</span>
          <span className="badge badge--ghost">DRAFT</span>
          <span className="badge badge--solid">NEU</span>
          <span className="tag">EU · DACH</span>
          <span className="tag">PERSONA · 47</span>
        </div>
      </div>
    </div>
  </div>
);

ABControls.Inputs = () => {
  const sliderValue = 12;
  return (
    <div className="ab ab-pad">
      <div className="ab-head">
        <div className="num">05</div>
        <div className="meta-stack">
          <div className="t-kicker t-kicker--accent">FORMS · UNDERLINE EDITORIAL + BOX TECHNICAL</div>
          <div className="title">Eingaben</div>
          <div className="coord-row">FELD-LABELS IN MONO CAPS · ORANGE FOCUS</div>
        </div>
      </div>
      <div className="grid-2" style={{ gap: 56 }}>
        <div className="group">
          <div className="group-label">Editorial — Hero-Forms</div>
          <div className="field">
            <label className="field-label">Fragestellung</label>
            <input className="input input--bare" placeholder="Was möchtest du dieses Dokument fragen?" defaultValue="Wie reagiert die Öffentlichkeit auf die EU-AI-Act Phase 2?" />
            <span className="field-hint">PFLICHTFELD · MIN. 12 ZEICHEN</span>
          </div>
          <div className="field" style={{ marginTop: 32 }}>
            <label className="field-label">Dokument</label>
            <div className="input-group">
              <span className="pfx">FILE</span>
              <input className="input" defaultValue="dossier-eu-ai-act-v3.pdf" />
              <span className="sfx">2.4 MB</span>
            </div>
          </div>

          <div className="group-label" style={{ marginTop: 32 }}>Tabular — kompakt</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="field">
              <label className="field-label">LLM Modell</label>
              <div className="select-trigger">
                <span>qwen3-coder-next:cloud</span>
                <span className="caret">▾</span>
              </div>
            </div>
            <div className="field">
              <label className="field-label">Sprache</label>
              <div className="select-trigger">
                <span>Deutsch (DE)</span>
                <span className="caret">▾</span>
              </div>
            </div>
            <div className="field">
              <label className="field-label">Persona-Limit</label>
              <input className="input" defaultValue="120" />
            </div>
            <div className="field">
              <label className="field-label">Laufdauer</label>
              <div className="input-group">
                <input className="input" defaultValue="14" />
                <span className="sfx">Tage</span>
              </div>
            </div>
          </div>

          <div className="field" style={{ marginTop: 24 }}>
            <label className="field-label">Notiz</label>
            <textarea className="textarea" rows="3" placeholder="Optional — wird im Report referenziert."></textarea>
          </div>
        </div>

        <div className="group">
          <div className="group-label">Slider · Range</div>
          <div className="field">
            <label className="field-label">Aktivitätsdichte · Posts pro Runde</label>
            <div className="slider-track">
              <span className="fill" style={{ width: `${(sliderValue / 24) * 100}%` }}></span>
              <span className="thumb" style={{ left: `${(sliderValue / 24) * 100}%` }}></span>
              <span className="thumb-label" style={{ left: `${(sliderValue / 24) * 100}%` }}>{sliderValue} / 24</span>
            </div>
            <div className="slider-ticks">
              <span>0</span><span>6</span><span>12</span><span>18</span><span>24</span>
            </div>
          </div>

          <div className="group-label" style={{ marginTop: 32 }}>Tabs</div>
          <div className="tabs">
            <button className="tab is-active">Personas <span className="count">214</span></button>
            <button className="tab">Verbindungen <span className="count">1.482</span></button>
            <button className="tab">Cluster <span className="count">14</span></button>
            <button className="tab">Audit-Log</button>
          </div>

          <div className="group-label" style={{ marginTop: 32 }}>Segmented</div>
          <div className="row">
            <div className="segmented">
              <button className="seg is-active">Graph</button>
              <button className="seg">Liste</button>
              <button className="seg">JSON</button>
            </div>
            <div className="segmented">
              <button className="seg">Round 1</button>
              <button className="seg is-active">Round 12</button>
              <button className="seg">Round 24</button>
            </div>
          </div>

          <div className="group-label" style={{ marginTop: 32 }}>Validierung Inline</div>
          <div className="field">
            <label className="field-label">Neo4j URI</label>
            <input className="input" defaultValue="bolt://localhost:7687" style={{ borderColor: "var(--status-success)" }} />
            <span className="field-hint" style={{ color: "var(--status-success)" }}>VERBUNDEN · 5.18.0 · 3 INDIZES</span>
          </div>
          <div className="field" style={{ marginTop: 16 }}>
            <label className="field-label">Embedding-Modell</label>
            <input className="input" defaultValue="qwen3-embedding:4b" style={{ borderColor: "var(--status-warn)" }} />
            <span className="field-hint" style={{ color: "var(--status-warn)" }}>VECTOR_DIM = 2560 · ANPASSUNG NÖTIG</span>
          </div>
        </div>
      </div>
    </div>
  );
};

window.ABControls = ABControls;
