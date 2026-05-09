/* Foundations: Identity · Color · Typography (v3 — Apple Enterprise) */

const ABF = {};

// ─── Brand glyph (refined) ──────────────────────────────────
function GlyphV3({ size = 32, color = "currentColor" }) {
  const s = size;
  return (
    <svg width={s} height={s} viewBox="0 0 32 32" fill="none">
      <defs>
        <linearGradient id="g3" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0A84FF"/>
          <stop offset="1" stopColor="#0040A0"/>
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#g3)"/>
      <path d="M9 22.5 L16 9.5 L23 22.5" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/>
      <line x1="11.8" y1="17.5" x2="20.2" y2="17.5" stroke="white" strokeWidth="2.4" strokeLinecap="round"/>
      <circle cx="16" cy="9.5" r="1.6" fill="white"/>
    </svg>
  );
}

function WordmarkV3({ size = 28, mono = false }) {
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      <GlyphV3 size={size} />
      <span style={{
        fontSize: size * 0.78, fontWeight: 600,
        letterSpacing: "-0.02em", color: "var(--text-primary)",
        fontFamily: "var(--font-sans)",
      }}>
        Agora
      </span>
    </div>
  );
}

// ─── 01 · Identity ──────────────────────────────────────────
ABF.Identity = () => (
  <div style={{ height: "100%", padding: 64, display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 48 }}>
    <div className="stack" style={{ justifyContent: "space-between" }}>
      <div className="hstack gap-3">
        <span className="t-section-head">Identity</span>
        <span className="t-section-head text-tertiary">· 01</span>
      </div>

      <div className="stack gap-6">
        <h1 className="t-hero" style={{ margin: 0 }}>
          A clearer view of<br/>
          <span style={{ color: "var(--accent)" }}>public reaction.</span>
        </h1>
        <p className="t-title-3" style={{ color: "var(--text-secondary)", maxWidth: "44ch", fontWeight: 400 }}>
          Agora is an enterprise platform for multi-agent reaction simulation. Upload a document, model a public, run a debate, and get an evidence-bound report — local-first, cloud-compatible.
        </p>
      </div>

      <div className="stack gap-4">
        <span className="t-section-head">Wordmark</span>
        <div style={{ padding: "28px 32px", background: "var(--surface-elevated)", borderRadius: "var(--r-7)", boxShadow: "0 0 0 1px var(--hairline)" }}>
          <WordmarkV3 size={48} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {[16, 24, 32, 48].map((s) => (
            <div key={s} style={{
              display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
              padding: 16, background: "var(--surface-elevated)",
              borderRadius: "var(--r-6)", boxShadow: "0 0 0 1px var(--hairline)",
            }}>
              <GlyphV3 size={s} />
              <span className="t-caption">{s}px</span>
            </div>
          ))}
        </div>
      </div>
    </div>

    <div className="stack gap-5" style={{ justifyContent: "center" }}>
      <div style={{
        position: "relative", aspectRatio: "1 / 1",
        borderRadius: "var(--r-9)", overflow: "hidden",
        background: "linear-gradient(135deg, #f5f5f7 0%, #ffffff 50%, #f0f0f2 100%)",
        boxShadow: "0 0 0 1px var(--hairline), var(--shadow-3)",
      }}>
        {/* Soft grid */}
        <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, opacity: 0.5 }}>
          <defs>
            <pattern id="gridv3" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M 32 0 L 0 0 0 32" fill="none" stroke="rgba(60,60,67,0.06)" strokeWidth="1"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#gridv3)"/>
        </svg>
        {/* Hero glyph */}
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <GlyphV3 size={220} />
        </div>
        {/* Bottom meta */}
        <div style={{
          position: "absolute", left: 24, right: 24, bottom: 24,
          display: "flex", justifyContent: "space-between", alignItems: "flex-end",
        }}>
          <div className="stack gap-1">
            <span className="t-caption text-tertiary">VERSION</span>
            <span className="t-headline">v0.9.0 · Persona Review</span>
          </div>
          <div className="stack gap-1" style={{ alignItems: "flex-end" }}>
            <span className="t-caption text-tertiary">DESIGN</span>
            <span className="t-headline">Enterprise · Light</span>
          </div>
        </div>
      </div>

      <div className="stack gap-2">
        <p className="t-callout" style={{ color: "var(--text-secondary)" }}>
          The wordmark sits on neutral surfaces. The mark is reproduced in <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Apple Blue</span>{" "}gradient and never on busy photography. Minimum padding equals the height of the glyph's stroke.
        </p>
      </div>
    </div>
  </div>
);

// ─── 02 · Color ─────────────────────────────────────────────
ABF.Color = () => {
  const Swatch = ({ name, hex, role, fg = "#000" }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--separator)" }}>
      <div style={{
        width: 56, height: 40, borderRadius: 8,
        background: hex,
        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.06)",
        flex: "none",
      }} />
      <div className="stack gap-1" style={{ flex: 1, minWidth: 0 }}>
        <span className="t-callout" style={{ fontWeight: 600 }}>{name}</span>
        <span className="t-footnote" style={{ color: "var(--text-secondary)" }}>{role}</span>
      </div>
      <span className="t-mono t-footnote" style={{ color: "var(--text-tertiary)" }}>{hex.toUpperCase()}</span>
    </div>
  );

  return (
    <div style={{ height: "100%", padding: 56, display: "flex", flexDirection: "column", gap: 24 }}>
      <div className="between">
        <div className="stack gap-2">
          <span className="t-section-head">Color · 02</span>
          <h2 className="t-largeTitle" style={{ margin: 0 }}>System palette</h2>
          <span className="t-body" style={{ color: "var(--text-secondary)" }}>One accent, restrained neutrals, semantic status. Light mode only.</span>
        </div>
        <div className="hstack gap-2">
          <span className="pill"><span className="dot"></span>WCAG AA</span>
          <span className="pill pill--blue"><span className="dot"></span>Single accent</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 28, flex: 1 }}>
        <div className="card card-pad">
          <div className="t-section-head" style={{ marginBottom: 8 }}>Surfaces & Text</div>
          <Swatch name="Base" hex="#FFFFFF" role="Page background" />
          <Swatch name="Canvas" hex="#F5F5F7" role="App canvas / sunken" />
          <Swatch name="Inset" hex="#F2F2F7" role="Inputs · grouped lists" />
          <Swatch name="Tint" hex="#FBFBFD" role="Sidebar · chrome" />
          <Swatch name="Hairline" hex="#D2D2D7" role="Borders · separators" />
          <Swatch name="Text Primary" hex="#1D1D1F" role="Body & titles" />
          <Swatch name="Text Secondary" hex="#6E6E73" role="Subtitles · meta" />
          <Swatch name="Text Tertiary" hex="#86868B" role="Captions · placeholders" />
        </div>

        <div className="card card-pad">
          <div className="t-section-head" style={{ marginBottom: 8 }}>Accent · Apple Enterprise Blue</div>
          <Swatch name="Accent" hex="#0066CC" role="Primary action · selection" />
          <Swatch name="Accent Hover" hex="#0052A3" role="Hover state" />
          <Swatch name="Accent Pressed" hex="#004080" role="Pressed state" />
          <div style={{ marginTop: 16 }}>
            <div className="t-section-head" style={{ marginBottom: 8 }}>Tinted (10% / 16%)</div>
            <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
              <div style={{ flex: 1, padding: 16, borderRadius: 10, background: "var(--accent-tint-bg)" }}>
                <span className="t-callout" style={{ color: "var(--accent-tint-text)", fontWeight: 600 }}>Tinted action</span>
              </div>
              <div style={{ flex: 1, padding: 16, borderRadius: 10, background: "var(--accent)" }}>
                <span className="t-callout" style={{ color: "#fff", fontWeight: 600 }}>Filled action</span>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 24 }}>
            <div className="t-section-head" style={{ marginBottom: 8 }}>System Grays</div>
            <div style={{ display: "flex", borderRadius: 8, overflow: "hidden", boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.06)" }}>
              {["#8e8e93","#aeaeb2","#c7c7cc","#d1d1d6","#e5e5ea","#f2f2f7"].map((c, i) => (
                <div key={i} style={{ flex: 1, height: 40, background: c }} title={c}/>
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              {["1","2","3","4","5","6"].map((n) => (
                <span key={n} className="t-caption">Gray {n}</span>
              ))}
            </div>
          </div>
        </div>

        <div className="card card-pad">
          <div className="t-section-head" style={{ marginBottom: 8 }}>Semantic Status</div>
          <Swatch name="Success" hex="#248A3D" role="Done · running healthy" />
          <Swatch name="Warning" hex="#B25000" role="Retry · degraded" />
          <Swatch name="Critical" hex="#C5292A" role="Error · failed" />
          <Swatch name="Info" hex="#007A87" role="Queued · processing" />
          <Swatch name="Branch" hex="#6E3CBC" role="Branch · scenario" />

          <div style={{ marginTop: 20 }}>
            <div className="t-section-head" style={{ marginBottom: 12 }}>In context</div>
            <div className="hstack" style={{ flexWrap: "wrap", gap: 8 }}>
              <span className="pill pill--green"><span className="dot"></span>Done</span>
              <span className="pill pill--orange"><span className="dot"></span>Retry</span>
              <span className="pill pill--red"><span className="dot"></span>Failed</span>
              <span className="pill pill--teal"><span className="dot"></span>Queued</span>
              <span className="pill pill--purple"><span className="dot"></span>Branch</span>
              <span className="pill pill--blue"><span className="dot"></span>Live</span>
            </div>
          </div>

          <div style={{ marginTop: 20, padding: 16, background: "var(--surface-canvas)", borderRadius: 10 }}>
            <div className="t-section-head" style={{ marginBottom: 6 }}>Rule</div>
            <p className="t-footnote" style={{ color: "var(--text-secondary)", margin: 0, lineHeight: 1.6 }}>
              Color carries semantic weight, never decoration. One <strong>accent</strong> per primary action, status colors only on pills, dots and inline validation. Surfaces stay neutral so data leads.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── 03 · Typography ────────────────────────────────────────
ABF.Type = () => {
  const Row = ({ name, spec, children, ...rest }) => (
    <div style={{
      display: "grid", gridTemplateColumns: "180px 1fr", gap: 32,
      padding: "20px 0", borderBottom: "1px solid var(--separator)",
      alignItems: "baseline",
    }}>
      <div className="stack gap-1">
        <span className="t-headline">{name}</span>
        <span className="t-footnote" style={{ color: "var(--text-secondary)" }}>{spec}</span>
      </div>
      <div {...rest}>{children}</div>
    </div>
  );

  return (
    <div style={{ height: "100%", padding: 56 }}>
      <div className="between" style={{ marginBottom: 28 }}>
        <div className="stack gap-2">
          <span className="t-section-head">Typography · 03</span>
          <h2 className="t-largeTitle" style={{ margin: 0 }}>San Francisco · System</h2>
          <span className="t-body" style={{ color: "var(--text-secondary)" }}>One family, structured scale. Geist as the open substitute when SF Pro is unavailable.</span>
        </div>
        <div className="hstack gap-2">
          <span className="pill">SF Pro Display</span>
          <span className="pill">SF Pro Text</span>
          <span className="pill">SF Mono</span>
        </div>
      </div>

      <div>
        <Row name="Hero" spec="64 / 66 · -2.8% · Semibold">
          <span className="t-hero">Multi‑agent simulation, ready for the room.</span>
        </Row>
        <Row name="Display" spec="48 / 52 · -2.4% · Semibold">
          <span className="t-display">214 personas. 14 clusters. 3 bridges.</span>
        </Row>
        <Row name="Large Title" spec="34 / 41 · -2.2% · Bold">
          <span className="t-largeTitle">Persona Library</span>
        </Row>
        <Row name="Title 1" spec="28 / 34 · -1.8% · Bold">
          <span className="t-title-1">A clearer view of public reaction.</span>
        </Row>
        <Row name="Title 2" spec="22 / 28 · -1.2% · Bold">
          <span className="t-title-2">Round 12 · Graph Build</span>
        </Row>
        <Row name="Headline" spec="17 / 22 · Semibold">
          <span className="t-headline">Persona 47 left the discussion after round 6.</span>
        </Row>
        <Row name="Body" spec="15 / 20 · Regular" style={{ maxWidth: "60ch" }}>
          <p className="t-body" style={{ margin: 0 }}>
            Upload a document. Agora extracts a knowledge graph, generates personas with stances and activity profiles, simulates a discussion, and produces an evidence‑bound report.
          </p>
        </Row>
        <Row name="Subhead" spec="13 / 18 · Medium">
          <span className="t-subhead">Last edited 27 Apr 2026 · 2.4 MB · dossier-eu-ai-act-v3.pdf</span>
        </Row>
        <Row name="Footnote" spec="12 / 16 · Regular">
          <span className="t-footnote">Local-first storage. Encrypted with FileVault. SOC 2 in audit.</span>
        </Row>
        <Row name="Caption" spec="11 / 13 · Medium · Caps">
          <span className="t-section-head">SECTION HEADER</span>
        </Row>
        <Row name="Mono" spec="13 / 18 · Geist Mono">
          <span className="t-mono t-callout">POST /api/simulation/&#123;sim_id&#125;/run · 200 OK · 142ms</span>
        </Row>
      </div>
    </div>
  );
};

window.ABF = ABF;
window.GlyphV3 = GlyphV3;
window.WordmarkV3 = WordmarkV3;
