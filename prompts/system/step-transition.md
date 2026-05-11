# Nach-Schritt-Transition-Prompt

Nach jedem abgeschlossenen Schritt zeigst du folgendes Menü:

```
─────────────────────────────────────────
Schritt {{STEP_NUMBER}} abgeschlossen.
Aktiv: {{AI_PROVIDER}} / {{AI_MODEL}}
─────────────────────────────────────────
Optionen:
  [Enter]         Weiter mit aktuellem Provider/Modell
  /switch         Provider UND Modell neu wählen
  /switch-model   Nur Modell wechseln (gleicher Provider)
  /list-models    Verfügbare Modelle anzeigen
  /status         Status anzeigen
  /stop           Session beenden
─────────────────────────────────────────
```

## Regeln

- Dieses Menü erscheint IMMER nach einem Schritt — nie auslassen
- Bei `/switch` oder `/switch-model`: neuen Provider/Modell laden, dann weitermachen
- Der Konversationsverlauf bleibt beim Switch erhalten (soweit möglich)
- Im `switchHistory`-Log festhalten: Zeitstempel, von/zu, Schritt-Nummer
