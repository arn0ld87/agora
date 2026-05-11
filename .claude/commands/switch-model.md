# /switch-model — Nur das Modell wechseln

> Wechselt nur das Modell beim aktuellen Provider — kein Provider-Wechsel.

## Ablauf

### Schritt 1 — Modelle des aktuellen Providers laden

```
Aktueller Provider: [current_provider]
Aktuelles Modell:  [current_model]

Verfügbare Modelle:
```

API-Aufruf wie in `/ai-init` beschrieben (für den aktuellen Provider).

### Schritt 2 — Auswahl

```
  1) modell-a    ← aktuell
  2) modell-b
  3) modell-c
  [Enter] — Abbrechen (bleibt bei [current_model])

Wähle [Nummer]: 
```

### Schritt 3 — Wechsel durchführen

- `model` im Session-State aktualisieren
- Switch-Event loggen (nur `model` ändert sich, `provider` bleibt gleich)
- Bestätigung:
  ```
  ✓ Modell gewechselt: [alt] → [neu]
  Provider bleibt: [current_provider]
  ```

## Tipp

Nützlich wenn du z.B. von `gpt-4o` zu `o3-mini` wechseln willst ohne den Provider zu ändern, oder von `llama3` zu `mistral` bei Ollama.
