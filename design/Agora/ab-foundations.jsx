/* Foundations artboards: identity, type, color, glyph */

const ABFoundations = {};

ABFoundations.Identity = () => (
  <div className="ab ab--grid ab-pad-lg">
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 64, height: "100%" }}>
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
        <div>
          <div className="t-kicker t-kicker--accent">№ 01 — IDENTITÄT · CARTOGRAPHIC NOTEBOOK</div>
          <h1 className="t-display" style={{ marginTop: 24, fontSize: 96 }}>
            Agor<span style={{ color: "var(--accent)" }}>·</span>a
          </h1>
          <p className="t-body" style={{ marginTop: 32, maxWidth: "44ch" }}>
            Eine redaktionelle Tool-Sprache für Multi-Agenten-Simulation. Cremetext auf fast-schwarzem Grund. Serif für Denken, Mono für Daten, Orange für Aktion, Plasma-Cyan für Selektion.
          </p>
        </div>
        <div className="row" style={{ gap: 48, marginTop: 48 }}>
          <div>
            <div className="meta-mono" style={{ marginBottom: 8 }}>Wortmarke + Glyphe</div>
            <AgoraLogo size={28} />
          </div>
          <div>
            <div className="meta-mono" style={{ marginBottom: 8 }}>Glyph isoliert</div>
            <AgoraGlyph size={48} />
          </div>
        </div>
        <hr className="rule-tick" style={{ marginTop: 48 }} />
        <div className="coord" style={{ marginTop: 16 }}>
          <span>52.5200°N</span><span className="sep">·</span>
          <span>13.4050°E</span><span className="sep">·</span>
          <span className="accent">v0.6.1 ALPHA</span>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 24, justifyContent: "center" }}>
        <div className="meta-mono">Glyph-Studien</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          {["alpha-node", "cluster", "crosshair"].map((s) => (
            <div key={s} style={{ border: "1px solid var(--rule)", padding: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 16, background: "var(--bg-sunken)" }}>
              <AgoraGlyph size={56} style={s} />
              <div className="meta-mono" style={{ color: "var(--fg)" }}>{s}</div>
            </div>
          ))}
        </div>
        <div className="meta-mono" style={{ marginTop: 16 }}>Tagline</div>
        <p className="t-quote" style={{ fontSize: 24 }}>
          „Lade ein Dokument. Höre, was die Welt darüber sagen würde."
        </p>
      </div>
    </div>
  </div>
);

ABFoundations.Color = () => {
  const mono = [
    ["--mono-50",  "#f6f2eb", "Foreground / Cream"],
    ["--mono-300", "#ada398", "Body Text"],
    ["--mono-400", "#8b8177", "Muted"],
    ["--mono-500", "#6a625a", "Meta"],
    ["--mono-700", "#37332f", "Hairline strong"],
    ["--mono-900", "#171514", "Elevated"],
    ["--mono-950", "#0d0c0c", "Page"],
  ];
  const accent = [
    ["--neon-orange", "#ff6a00", "Primary action / Live"],
    ["--plasma-400", "#5ab4c8", "Selection / Info / Edges"],
  ];
  const status = [
    ["--status-success", "#6ea870", "Success · Done"],
    ["--status-warn",    "#d6a154", "Warning"],
    ["--status-error",   "#c25a5a", "Error"],
    ["--status-info",    "#5ab4c8", "Info / Queued"],
  ];
  const Row = ({ items }) => (
    <div className="swatch-row">
      {items.map(([tok, hex, role]) => (
        <div className="swatch" key={tok}>
          <span className="chip" style={{ background: hex }}></span>
          <div className="name">{tok}<span className="role">{role}</span></div>
          <span className="hex">{hex.toUpperCase()}</span>
        </div>
      ))}
    </div>
  );
  return (
    <div className="ab ab-pad">
      <div className="ab-head">
        <div className="num">02</div>
        <div className="meta-stack">
          <div className="t-kicker t-kicker--accent">PALETTE · MONO + ZWEI ACHSEN</div>
          <div className="title">Farbsystem</div>
          <div className="coord-row">11 STUFEN MONO · 1 PRIMÄR · 1 SEKUNDÄR · 4 STATUS</div>
        </div>
      </div>
      <div className="grid-3">
        <div>
          <div className="group-label" style={{ paddingBottom: 8, borderBottom: "1px solid var(--rule)", marginBottom: 12 }}>Mono-Skala</div>
          <Row items={mono} />
        </div>
        <div>
          <div className="group-label" style={{ paddingBottom: 8, borderBottom: "1px solid var(--rule)", marginBottom: 12 }}>Akzente</div>
          <Row items={accent} />
          <div className="group-label" style={{ paddingBottom: 8, borderBottom: "1px solid var(--rule)", marginTop: 32, marginBottom: 12 }}>Status</div>
          <Row items={status} />
        </div>
        <div>
          <div className="group-label" style={{ paddingBottom: 8, borderBottom: "1px solid var(--rule)", marginBottom: 12 }}>Regel</div>
          <p className="t-body-sm" style={{ color: "var(--fg-body)" }}>
            Orange ist <em style={{ color: "var(--fg)", fontStyle: "normal" }}>einmal pro Screen</em>. Plasma-Cyan ist die zweite Achse: Selektion, Info, Graph-Edges. Status-Farben nur in Badges, Toasts, Inline-Validierung — nicht als Flächen.
          </p>
          <hr className="hairline" style={{ margin: "24px 0" }} />
          <div className="meta-mono" style={{ marginBottom: 12 }}>Akzent gegen Akzent</div>
          <div className="row" style={{ gap: 8 }}>
            <span className="badge badge--accent"><span className="dot"></span>LIVE</span>
            <span className="badge badge--plasma"><span className="dot"></span>SELECTED · 12</span>
            <span className="badge badge--success"><span className="dot"></span>DONE</span>
            <span className="badge badge--warn"><span className="dot"></span>RETRY</span>
            <span className="badge badge--error"><span className="dot"></span>500</span>
            <span className="badge"><span className="dot"></span>QUEUED</span>
          </div>
        </div>
      </div>
    </div>
  );
};

ABFoundations.Type = () => (
  <div className="ab ab-pad">
    <div className="ab-head">
      <div className="num">03</div>
      <div className="meta-stack">
        <div className="t-kicker t-kicker--accent">TYPOGRAFIE · DREI FAMILIEN</div>
        <div className="title">Schriftrollen</div>
        <div className="coord-row">FRAUNCES · GEIST · GEIST MONO</div>
      </div>
    </div>
    <div>
      <div className="type-row">
        <div className="label">DISPLAY<small>Fraunces 300 · -2%</small></div>
        <div className="t-display" style={{ fontSize: 80 }}>Wissen<br/>kartiert.</div>
      </div>
      <div className="type-row">
        <div className="label">HEADLINE<small>Fraunces 400</small></div>
        <div className="t-headline" style={{ fontSize: 48 }}>Eine Multi-Agenten-Simulation für öffentliche Reaktionen.</div>
      </div>
      <div className="type-row">
        <div className="label">TITLE<small>Fraunces 400 · 32px</small></div>
        <div className="t-title">Persona-Bibliothek</div>
      </div>
      <div className="type-row">
        <div className="label">SUBTITLE<small>Geist 400 · 20px</small></div>
        <div className="t-subtitle">214 Agenten, 14 Cluster, 3 Bridge-Knoten.</div>
      </div>
      <div className="type-row">
        <div className="label">BODY<small>Geist 400 · 16px</small></div>
        <div className="t-body" style={{ maxWidth: "60ch" }}>
          Du lädst ein Dokument hoch, Agora extrahiert daraus einen Wissensgraphen, erzeugt Agenten-Personas mit Rollen, Haltungen und Aktivitätsprofilen, simuliert Diskussionen und erstellt danach einen Report.
        </div>
      </div>
      <div className="type-row">
        <div className="label">META<small>Geist 400 · 13px</small></div>
        <div className="t-meta">Datei: dossier-eu-ai-act-v3.pdf · 2,4 MB · zuletzt geändert 27. April 2026</div>
      </div>
      <div className="type-row">
        <div className="label">KICKER<small>Geist Mono · 11px · 0.24em</small></div>
        <div><span className="t-kicker t-kicker--accent">№ 04 · ROUND 12 · GRAPH BUILD</span></div>
      </div>
      <div className="type-row">
        <div className="label">CODE / DATA<small>Geist Mono · 13px</small></div>
        <div className="mono" style={{ color: "var(--mono-100)" }}>
          POST /api/simulation/&#123;sim_id&#125;/run · 200 OK · 142ms
        </div>
      </div>
      <div className="type-row">
        <div className="label">QUOTE<small>Fraunces italic · 28px</small></div>
        <div className="t-quote" style={{ fontSize: 28, maxWidth: "32ch" }}>
          „Persona 47 verlässt die Diskussion nach Runde 6."
        </div>
      </div>
    </div>
  </div>
);

window.ABFoundations = ABFoundations;
