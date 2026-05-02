/* Overlays artboards: menu, command palette, modal, drawer, tooltip, toast */

const ABOverlays = {};

ABOverlays.MenusAndCmdK = () => (
  <div className="ab ab-pad">
    <div className="ab-head">
      <div className="num">06</div>
      <div className="meta-stack">
        <div className="t-kicker t-kicker--accent">MENUS · DROPDOWNS · COMMAND PALETTE</div>
        <div className="title">Navigation in der Tiefe</div>
        <div className="coord-row">⌘K · KEYBOARD-FIRST · MONO LABELS</div>
      </div>
    </div>
    <div className="grid-2" style={{ gap: 56, alignItems: "start" }}>
      <div className="group">
        <div className="group-label">Dropdown · Modell wählen</div>
        <div className="popover" style={{ width: 320 }}>
          <div className="menu">
            <div className="menu-section-label">Cloud · Ollama</div>
            <div className="menu-item is-active">
              <span><span className="glyph">▸</span> qwen3-coder-next:cloud</span>
              <span className="kbd">DEFAULT</span>
            </div>
            <div className="menu-item">
              <span><span className="glyph"> </span> claude-sonnet-4.5</span>
              <span className="kbd">CLOUD</span>
            </div>
            <div className="menu-divider"></div>
            <div className="menu-section-label">Lokal</div>
            <div className="menu-item">
              <span><span className="glyph"> </span> qwen2.5:32b</span>
              <span className="kbd">19.2 GB</span>
            </div>
            <div className="menu-item">
              <span><span className="glyph"> </span> llama3.1:70b</span>
              <span className="kbd">42.0 GB</span>
            </div>
            <div className="menu-divider"></div>
            <div className="menu-item">
              <span><span className="glyph">+</span> Modell hinzufügen</span>
              <span className="kbd-key">N</span>
            </div>
          </div>
        </div>

        <div className="group-label" style={{ marginTop: 32 }}>Kontext-Menü · Persona</div>
        <div className="popover" style={{ width: 280 }}>
          <div className="menu">
            <div className="menu-item"><span>Profil ansehen</span><span className="kbd-key">↵</span></div>
            <div className="menu-item"><span>In Bibliothek speichern</span><span className="kbd-key">S</span></div>
            <div className="menu-item"><span>Interview führen</span><span className="kbd-key">I</span></div>
            <div className="menu-divider"></div>
            <div className="menu-item"><span>Aus Simulation entfernen</span><span className="kbd"><span className="kbd-key">⇧</span><span className="kbd-key" style={{ marginLeft: 4 }}>⌫</span></span></div>
            <div className="menu-item" style={{ color: "var(--status-error)" }}><span>Persona löschen</span><span className="kbd-key">⌫</span></div>
          </div>
        </div>
      </div>

      <div className="group">
        <div className="group-label">Command Palette · ⌘K</div>
        <div className="cmdk">
          <div className="cmdk-input">
            <span className="glyph mono" style={{ color: "var(--accent)" }}>⌘K</span>
            <input defaultValue="persona" />
            <span className="meta-mono">12 RESULTS</span>
          </div>
          <div className="cmdk-result-set">
            <div className="menu">
              <div className="menu-section-label">Aktionen</div>
              <div className="menu-item is-active">
                <span><span className="glyph">▸</span> Personas neu generieren</span>
                <span className="kbd"><span className="kbd-key">⌘</span><span className="kbd-key" style={{ marginLeft: 4 }}>G</span></span>
              </div>
              <div className="menu-item">
                <span><span className="glyph"> </span> Persona-Bibliothek öffnen</span>
                <span className="kbd-key">L</span>
              </div>
              <div className="menu-section-label">Springen zu</div>
              <div className="menu-item">
                <span><span className="glyph"> </span> Step 2 · Environment Setup</span>
                <span className="kbd"><span className="kbd-key">G</span><span className="kbd-key" style={{ marginLeft: 4 }}>2</span></span>
              </div>
              <div className="menu-item">
                <span><span className="glyph"> </span> Persona № 47 — Markus Renner</span>
                <span className="meta-mono">PERSONA</span>
              </div>
              <div className="menu-item">
                <span><span className="glyph"> </span> Persona № 112 — Lina Voß</span>
                <span className="meta-mono">PERSONA</span>
              </div>
            </div>
          </div>
          <div className="panel-foot" style={{ borderTop: "1px solid var(--rule)", padding: "10px 14px" }}>
            <span className="meta-mono">↑↓ NAVIGIEREN · ↵ AUSWÄHLEN · ESC SCHLIESSEN</span>
            <span className="meta-mono" style={{ color: "var(--accent)" }}>v0.6.1</span>
          </div>
        </div>

        <div className="group-label" style={{ marginTop: 32 }}>Tooltips</div>
        <div className="row" style={{ gap: 24, alignItems: "flex-start" }}>
          <div className="tooltip">PERSONA · 47 · MARKUS RENNER</div>
          <div className="tooltip tooltip--dark">⌘ + K — KOMMANDOPALETTE</div>
        </div>
      </div>
    </div>
  </div>
);

ABOverlays.ModalAndToasts = () => (
  <div className="ab ab-pad" style={{ background: "var(--mono-950)" }}>
    <div className="ab-head">
      <div className="num">07</div>
      <div className="meta-stack">
        <div className="t-kicker t-kicker--accent">MODAL · DRAWER · TOAST · POPOVER</div>
        <div className="title">Overlays</div>
        <div className="coord-row">EDITORIAL: KEINE ROUNDED CARDS · HAIRLINE-RAHMEN</div>
      </div>
    </div>
    <div className="grid-2" style={{ gap: 48, alignItems: "start" }}>
      <div>
        <div className="group-label">Bestätigungs-Modal</div>
        <div className="modal-back">
          <div className="modal" style={{ margin: "0 auto" }}>
            <div className="panel-head">
              <div className="title-line">
                <span className="t-kicker t-kicker--accent">№ ENTSCHEIDUNG</span>
                <span className="meta-mono">SIM-04F2</span>
              </div>
              <button className="btn btn--icon btn--ghost btn--sm" aria-label="Close"><span className="glyph">×</span></button>
            </div>
            <div className="panel-body">
              <h3 className="t-title" style={{ fontSize: 24, margin: 0 }}>Simulation verwerfen?</h3>
              <p className="t-body" style={{ marginTop: 12 }}>
                Du verwirfst <span style={{ color: "var(--fg)" }}>214 Personas</span>, <span style={{ color: "var(--fg)" }}>12 abgeschlossene Runden</span> und einen halbfertigen Report. Die Graph-Daten in Neo4j bleiben erhalten.
              </p>
              <hr className="hairline" style={{ margin: "20px 0" }} />
              <div className="meta-mono" style={{ marginBottom: 8 }}>BESTÄTIGEN MIT</div>
              <input className="input" placeholder="SIM-04F2 eintippen" />
            </div>
            <div className="panel-foot">
              <span className="meta-mono">ESC · ABBRECHEN</span>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn btn--ghost">Abbrechen</button>
                <button className="btn btn--danger">Verwerfen</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="group-label">Toast-Stack</div>
        <div className="col" style={{ gap: 12 }}>
          <div className="toast" style={{ borderLeftColor: "var(--status-success)" }}>
            <span className="status-dot status-dot--done" style={{ marginTop: 4 }}></span>
            <div className="body">
              <div className="title">Simulation abgeschlossen</div>
              <div className="desc">SIM-04F2 · 24 Runden · 214 Personas · 1.482 Posts</div>
              <div className="meta">REPORT BEREIT · IN 04:12 GENERIERT</div>
            </div>
          </div>
          <div className="toast">
            <span className="status-dot status-dot--running" style={{ marginTop: 4 }}></span>
            <div className="body">
              <div className="title">Round 13 / 24 läuft</div>
              <div className="desc">Markus Renner antwortet auf Lina Voß.</div>
              <div className="meta">142 MS · LLM CALL #1.847</div>
            </div>
          </div>
          <div className="toast" style={{ borderLeftColor: "var(--status-warn)" }}>
            <span className="status-dot status-dot--error" style={{ background: "var(--status-warn)", marginTop: 4 }}></span>
            <div className="body">
              <div className="title">Ollama langsam — JSON-Mode wird wiederholt</div>
              <div className="desc">2. Versuch in 4 Sekunden.</div>
              <div className="meta">RETRY × 2 · GRACEFUL</div>
            </div>
          </div>
        </div>

        <div className="group-label" style={{ marginTop: 32 }}>Popover · Persona-Hover</div>
        <div className="popover" style={{ width: 320 }}>
          <div className="panel-body" style={{ padding: 16 }}>
            <div className="row" style={{ gap: 12 }}>
              <div style={{ width: 44, height: 44, border: "1px solid var(--rule-strong)", background: "var(--bg-sunken)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--ff-serif)", fontSize: 20 }}>M</div>
              <div>
                <div className="t-subtitle" style={{ fontSize: 16 }}>Markus Renner</div>
                <div className="meta-mono">PERSONA · 47 · BRIDGE</div>
              </div>
            </div>
            <hr className="hairline" style={{ margin: "12px 0" }} />
            <p className="t-body-sm" style={{ margin: 0, color: "var(--fg-body)" }}>
              43 J · München · skeptisch ggü. KI-Regulierung · technisch versiert · postet 4×/Tag.
            </p>
            <div className="row" style={{ gap: 6, marginTop: 10 }}>
              <span className="tag">EU · DACH</span>
              <span className="tag">SKEPTISCH</span>
              <span className="tag">CLUSTER #3</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
);

window.ABOverlays = ABOverlays;
