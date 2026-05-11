# Codex – Multi-Provider Plan

> **Ziel:** Codex (OpenAI Codex CLI) kann beim Start und nach jedem Schritt den KI-Anbieter und das Modell wechseln. Unterstützte Anbieter: **OpenAI**, **Gemini**, **Ollama**. Modelle werden automatisch per API geladen.

---

## Architektur-Übersicht

```
agora/
├── docs/archive/old-plans/CODEX_PLAN.md              ← dieser Plan
├── .codex/
│   ├── config.json            ← aktiver Provider + Modell (Laufzeitkonfiguration)
│   └── instructions.md        ← globaler System-Prompt für Codex
├── .claude/commands/          ← bestehende Slash-Commands
│   ├── provider-switch.md     ← /provider-switch – Anbieter & Modell wechseln
│   ├── provider-list.md       ← /provider-list – verfügbare Modelle anzeigen
│   └── provider-status.md     ← /provider-status – aktuellen Status anzeigen
└── scripts/
    ├── codex-start.sh         ← Startskript mit Provider-Auswahl
    ├── list-models.sh         ← Modelle per API abrufen
    └── switch-provider.sh     ← Provider-Wechsel zur Laufzeit
```

---

## Phase 1 – Provider-Auswahl beim Start

### Ziel
Beim Aufruf von `codex` (oder `./scripts/codex-start.sh`) wird ein interaktives Menü angezeigt:

```
┌─────────────────────────────────┐
│  Agora Codex – Provider wählen  │
├─────────────────────────────────┤
│  1) OpenAI  (API Key benötigt)  │
│  2) Gemini  (API Key benötigt)  │
│  3) Ollama  (lokal, kein Key)   │
└─────────────────────────────────┘
Auswahl [1-3]:
```

Danach wird automatisch die Modellliste per API abgerufen und zur Auswahl angeboten.

### Flow
```
codex-start.sh
  └─ Provider wählen
       └─ list-models.sh <provider>
            └─ Modell wählen
                 └─ .codex/config.json schreiben
                      └─ codex --model <model> --provider <provider> starten
```

---

## Phase 2 – Modelle automatisch per API laden

### OpenAI
```bash
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | jq -r '.data[].id' | grep -E 'gpt|o[1-9]|codex' | sort
```

### Gemini
```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" \
  | jq -r '.models[].name' | sed 's|models/||' | sort
```

### Ollama
```bash
curl -s http://localhost:11434/api/tags \
  | jq -r '.models[].name' | sort
```

---

## Phase 3 – Provider/Modell-Wechsel nach jedem Schritt

Nach jeder abgeschlossenen Aktion kann Codex über den Slash-Command `/provider-switch` den Anbieter oder das Modell wechseln, ohne die Session zu beenden.

**Wechsel-Ablauf:**
1. `/provider-switch` aufrufen
2. Neuen Provider wählen (oder aktuellen behalten)
3. Modelle werden neu per API geladen
4. Modell wählen
5. `.codex/config.json` wird aktualisiert
6. Nächster Schritt läuft mit neuem Modell

---

## Phase 4 – Slash Commands

| Command | Datei | Funktion |
|---|---|---|
| `/provider-switch` | `.claude/commands/provider-switch.md` | Provider + Modell wechseln |
| `/provider-list` | `.claude/commands/provider-list.md` | Verfügbare Modelle anzeigen |
| `/provider-status` | `.claude/commands/provider-status.md` | Aktiven Provider anzeigen |

---

## Konfigurationsformat `.codex/config.json`

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "updated_at": "2026-05-11T03:52:00Z",
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "env_key": "OPENAI_API_KEY"
    },
    "gemini": {
      "base_url": "https://generativelanguage.googleapis.com/v1beta",
      "env_key": "GEMINI_API_KEY"
    },
    "ollama": {
      "base_url": "http://localhost:11434",
      "env_key": null
    }
  }
}
```

**Wichtig:** API-Keys niemals in `.codex/config.json` speichern – nur Env-Variablen-Namen referenzieren.

---

## Umgebungsvariablen (`.env.example`-Ergänzungen)

```bash
# Codex Provider Keys
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
# Ollama: kein Key, nur URL
OLLAMA_BASE_URL=http://localhost:11434

# Codex Standard-Einstellungen (optional)
CODEX_DEFAULT_PROVIDER=ollama
CODEX_DEFAULT_MODEL=llama3
```

---

## Offene Punkte / TODOs

- [ ] `scripts/codex-start.sh` implementieren
- [ ] `scripts/list-models.sh` implementieren  
- [ ] `scripts/switch-provider.sh` implementieren
- [ ] `.codex/config.json` Default-Template anlegen
- [ ] `.codex/instructions.md` mit Agora-Kontext befüllen
- [ ] Slash Commands in `.claude/commands/` anlegen
- [ ] `.env.example` mit Provider-Keys ergänzen
- [ ] Ollama-Fallback testen (kein Key nötig)
- [ ] Gemini-Modellnamen-Mapping prüfen (OpenAI-kompatibler Mode)
