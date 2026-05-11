# /status — Aktuellen AI-Status anzeigen

> Zeigt den vollständigen Status der aktuellen AI-Session.

## Ausgabe

```
╔══════════════════════════════════════╗
║         Agora AI — Session Status   ║
╠══════════════════════════════════════╣
║  Provider  : [provider]             ║
║  Modell    : [model]                ║
║  Schritt   : [step_number]          ║
║  Nachrichten: [message_count]       ║
╠══════════════════════════════════════╣
║  Switch-History:                    ║
║  [leer / oder Liste der Wechsel]    ║
╠══════════════════════════════════════╣
║  Env-Check:                         ║
║  OPENAI_API_KEY  : [gesetzt/fehlt]  ║
║  GEMINI_API_KEY  : [gesetzt/fehlt]  ║
║  OLLAMA_BASE_URL : [URL / default]  ║
╚══════════════════════════════════════╝
```

## Regeln

- API Keys **nie** im Klartext zeigen — nur `[gesetzt]` oder `[fehlt]`
- Switch-History zeigt: Zeitstempel, von/zu Provider/Modell, nach welchem Schritt
- Wenn keine Switches stattgefunden haben: `Switch-History: keine`

## Schnell-Aktionen nach /status

```
Optionen:
  /switch        — Provider + Modell wechseln
  /switch-model  — Nur Modell wechseln
  /list-models   — Modelle anzeigen
```
