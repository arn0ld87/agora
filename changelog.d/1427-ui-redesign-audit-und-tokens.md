### Changed (UI-Redesign 2026-09, Audit + PR 1 Tokens — 2026-09-05)

- **Visuelles Audit der gerenderten App** mit Scores, Top-15-Problemen, Designrichtung, Design-System und 10-PR-Plan unter `docs/ui/premium-redesign-2026-09/` (Ist-Screenshots, Vorlagen, drei Zielversionen für Ablage/Simulation/Bericht als HTML). (#1427)
- **`tokens-v3.css` entkernt:** acht Typo-Rollen (`--fs-display` fluid … `--fs-mono-lg`), Radius-Skala 4/6/10/pill, semantische Namen (`--bg-*`, `--border-*`, `--text-muted`, `--accent-live`, `--status-warning`), Motion-Tokens. Body-Text 15 → 14 px. (#1427)
- **`tokens-compat.css` abgespalten:** nur noch referenzierte v1/v2-Aliase, 75 tote Tokens (Mesh, Grid, Glow, Paper, Ink-Skala) entfernt. (#1427)
- **Label-Stil:** Tabellenköpfe, KPI-Labels, Abschnitts-Kicker, Menü-Labels, `.meta` in Satzschrift ohne Versalien; Mono nur noch für IDs und Zahlen. (#1427)
- **Logo-Glyph** auf Kupfer statt Blau. (#1427)
