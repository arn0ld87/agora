### Changed (UI-Redesign 2026-09, PR 2 Chrome bereinigen — 2026-09-05)

- **LOGS-FAB entfernt:** globale, feste FAB in `App.vue` ersetzt durch ein 20px-Icon "Protokoll" in beiden Kopfzeilen (`Topbar.vue`, `ShellRoot.vue`); Zustand + Ctrl/Cmd+Shift+L-Shortcut leben jetzt in `useLogDrawer.ts` (Single Source of Truth, analog `useCommandPalette.ts`). (#1436)
- **⌘K-Chip vereinheitlicht:** beide Kopfzeilen zeigen jetzt "Suchen ⌘K" mit identischem Markup/Styling (`.kbd`-Klasse, Tokens statt hartkodierter Werte); vorher Icon-only in `Topbar.vue`, Mono-Chip in `ShellRoot.vue`. (#1436)
- **Brand-Ring statt Glyph:** `AgoraBrand.vue` bekommt `mode="ring"` (reine CSS-Form, kein Asset) — `Sidebar.vue` zeigt jetzt den Kupfer-Ring statt des blau-violetten SVG-Glyphen. (#1436)
- **"?"-Fallback entfernt:** `UserMenu.vue` zeigte ohne Profil ein Fragezeichen als Avatar-Initiale — fällt jetzt zuerst auf den Benutzernamen, sonst auf ein neutrales Personen-Symbol zurück. Zusätzlich ein "Hilfe"-Eintrag im Menü (README-Anker, neuer Tab, opener-los). (#1436)
- **`/feed` im Shell:** `StepSimulationFeedView.vue` war shell-los ohne Rückweg — jetzt in `AppShell` + `PageHeader` gewrappt, analog `StepReportView.vue`, mit Rückweg-Breadcrumb zur Simulations-Pipeline. (#1436)
