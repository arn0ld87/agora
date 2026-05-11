# /switch — Provider und Modell wechseln

> Wechselt den KI-Anbieter UND das Modell innerhalb einer laufenden Session.

## Ablauf

### Schritt 1 — Aktuellen Status zeigen

```
Aktuelle Konfiguration:
  Provider : [current_provider]
  Modell   : [current_model]
  Schritt  : [current_step]

Neuen Provider wählen:
  1) openai
  2) gemini
  3) ollama
  [Enter] — Abbrechen
```

### Schritt 2 — Modelle des neuen Providers laden

Rufe die API des gewählten Providers auf (siehe `/ai-init` für die curl-Befehle).

### Schritt 3 — Modell wählen

```
Verfügbare Modelle für [neuer Provider]:
  1) modell-a
  2) modell-b
  ...
Wähle [Nummer]: 
```

### Schritt 4 — Switch durchführen

- Session-State aktualisieren: `provider` und `model`
- Switch-Event in `switchHistory` loggen:
  ```json
  {
    "at": "[ISO-Timestamp]",
    "from": { "provider": "[alt]", "model": "[alt]" },
    "to":   { "provider": "[neu]", "model": "[neu]" },
    "step": [aktuelle Schritt-Nummer]
  }
  ```
- Bestätigung ausgeben:
  ```
  ✓ Gewechselt zu [neuer Provider] / [neues Modell]
  Kontext-History bleibt erhalten.
  ```

## Hinweis

- Nur Modell wechseln (gleicher Provider): `/switch-model`
- Status prüfen: `/status`
