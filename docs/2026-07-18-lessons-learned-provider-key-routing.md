# Lessons Learned 2026-07-18 — Provider-Wechsel, Key-Routing & Thinking

**Kontext:** Fortsetzung des Arbeitsprotokolls
[`2026-07-18-sim-agenten-stumm-arbeitsprotokoll.md`](2026-07-18-sim-agenten-stumm-arbeitsprotokoll.md).
Ziel war, Simulationen mit Gemini bzw. MiniMax lauffähig zu machen. Dabei
haben sich mehrere Diagnosen des ursprünglichen Protokolls als **falsch oder
unvollständig** herausgestellt. Dieses Dokument hält den verifizierten Stand
fest.

## TL;DR

1. **Der `models/`-Prefix war NICHT die Ursache.** Der Gemini-OpenAI-Compat-
   Endpoint akzeptiert `gemini-2.5-flash-lite` **und** `models/gemini-2.5-flash-lite`
   (beide HTTP 200, live verifiziert). Der 404 „model not found" war ein
   **Key-/Access-Problem**, kein Namensformat-Problem. → Der spekulative
   Prefix-Strip-Fix wurde wieder zurückgenommen.
2. **Der eigentliche, wiederkehrende Blocker ist Key-Routing-Divergenz.** Die
   Sim-Prep-Generatoren (Persona/Config) ziehen den API-Key aus
   `Config.LLM_API_KEY` (dem `.env`-Fallback = Ollama-Key) statt aus dem
   UI-Secrets-Store. Deshalb bricht **jeder** Provider-Wechsel über die UI.
   → Eigenes Follow-up-Issue.
3. **MiniMax-Thinking lässt sich nur mit `MiniMax-M3` abschalten** (`thinking:
   {"type":"disabled"}`). Die `-highspeed`-Modelle (M2.x) ignorieren das Flag.
4. **Der „Runde-1-Hänger" war ein einmaliger HF-Modell-Download**
   (`Twitter/twhin-bert-base`, ~1,1 GB, unauthenticated → rate-limited).

## Verifizierte Befunde

### 1. 404 „model not found" = Key/Access, nicht Modellname

Live-Probe gegen den Gemini-Endpoint mit dem Store-Key (beide Formen):

| Modell-String | Ergebnis |
|---|---|
| `gemini-2.5-flash-lite` | HTTP 200 |
| `models/gemini-2.5-flash-lite` | HTTP 200 |

Der 404 trat nur auf, solange der **alte/falsche Key** im Store lag. Sobald der
korrekte (paid) Key aktiv war, funktionierten beide Formen. **Merksatz:** Bei
`404 not_found` auf einem funktionierenden Endpoint zuerst **Key/Account-Zugriff**
prüfen (Modell-Liste des Providers gegen den Key auflisten), nicht am
Modellnamen basteln.

Diagnose-Technik (token-arm, ohne Secret-Leak), im Container:

```python
c = LLMClient()                      # liest active_llm_config + Store-Key
ids = [m.id for m in c.client.models.list().data]   # zeigt gültige Modell-IDs
c.client.chat.completions.create(model="…", messages=[…], max_tokens=5)  # 200/4xx
```

### 2. Key-Routing-Divergenz (Kern-Bug, offen)

Belegt über Metadaten (keine Secret-Werte):

| Quelle | Key | für aktiven Provider korrekt? |
|---|---|---|
| UI-Secrets-Store (`SecretResolver.get_api_key`) | len 125 (`sk-cp-…`, MiniMax) | ✓ |
| `active_llm_config.json` | provider=minimax, MiniMax-M3 | ✓ |
| `resolve_route_api_key(minimax-route)` | liefert den Store-Key | ✓ |
| **`Config.LLM_API_KEY`** (`.env`-Fallback) | len 24 (`agora-…`, Ollama) | ✗ |

`SimulationConfigGenerator` und `OasisProfileGenerator` haben
`self.api_key = api_key or Config.LLM_API_KEY`. Wird beim Prepare→Generator-
Handoff kein aufgelöster Store-Key durchgereicht, greift der Ollama-`.env`-Key
→ Requests an den (korrekt aufgelösten) Provider-Endpoint mit falschem Key →
`404`/`401`. Das ist die im Auto-Memory notierte „Legacy-llm_profile/Config-
Fallback"-Divergenz.

**Konsequenz:** Der Backend-`LLMClient` (Report/Chat) funktioniert, weil er
`active_llm_config` + Store nutzt; die **Sim-Prep** nicht. Deshalb wirken Sims
„stumm", obwohl Provider und Key eigentlich korrekt hinterlegt sind.

### 3. MiniMax-Thinking (per OpenAI-Compat-Spec)

`ChatCompletionReq.thinking.type ∈ {"disabled","adaptive"}`:

- `disabled` — schaltet Reasoning **nur bei MiniMax-M3** ab (direkte Antwort,
  keine `<think>`-Tokens). **M2.x ignorieren es** (Thinking bleibt an).
- `adaptive` — Default.

Live verifiziert: `MiniMax-M3` + `disabled` → `Hey!` (kein `<think>`);
`MiniMax-M2.5-highspeed` + `disabled` → weiterhin `<think>…`. Für „schnell ohne
Thinking" ist also **M3** die einzige korrekte Wahl. Zusatznutzen: ohne
`<think>`-Präfix zerschießen die Antworten die JSON-Config-/Report-Parser nicht.

### 4. „Runde-1-Hänger" = HF-Cold-Download

Der OASIS-Subprozess lädt beim ersten Lauf `Twitter/twhin-bert-base` (~1,1 GB)
von HuggingFace. Unauthenticated ist der Download rate-limited und blockiert die
erste Runde minutenlang. Danach gecacht. → `HF_TOKEN`-Passthrough beschleunigt
künftige Downloads.

## Was in diesem PR geändert wurde

- **Track B — Store statt `.env` für Gemini-OASIS:** `build_route_subprocess_env`
  injiziert den Store-Key zusätzlich als `GEMINI_API_KEY` (CAMEL liest den, nicht
  `GOOGLE_API_KEY`). Beseitigt die `Missing GEMINI_API_KEY`-Crash-Falle.
  Defensiver Fallback mit korrekter Präzedenz in `create_model`.
- **MiniMax-Thinking:** `build_minimax_extra_body` (OASIS/CAMEL) +
  `_minimax_thinking_extra_body` (LLMClient, `chat`/`chat_json`/tool-calls).
  Nur für `api.minimax.io`, gekoppelt an den bestehenden `think`-Toggle
  (`OLLAMA_THINKING`/`reasoning_effort`).
- **HF-Token:** `HF_TOKEN=${HF_TOKEN:-}`-Passthrough in `docker-compose.yml`.
- **Localhost-Falle:** `scripts/check_llm_endpoint_localhost.sh` +
  `scripts/fix-llm-localhost-falle.sh` + `routing`-Scope im Pre-Push-Gate.

Alles test-first (Registry-, Routing-Seed-, `_sim_common`-, OASIS-Dispatch- und
LLMClient-Tests). Der zurückgenommene Prefix-Fix ist **nicht** enthalten.

## Offen (Follow-up-Issue)

**Key-Routing-Divergenz beheben:** Sim-Prep-Generatoren müssen den API-Key über
denselben Pfad auflösen wie der Backend-`LLMClient` (active_llm_config + Store /
`resolve_route_api_key`) statt über `Config.LLM_API_KEY`. Erst danach werden
UI-Provider-Wechsel für Simulationen zuverlässig.

Weitere, separate Baustellen (nicht Teil dieses PRs):

- Report-Outline: schwaches Modell + `LLM_DISABLE_JSON_MODE=true` → das Modell
  lässt Pflichtfelder (`title`) weg → `PlanResponse`-Validation-Errors.
- Report-Embedding: ungültiger OpenAI-Embedding-Key → 401, degradiert auf
  lokale Suche.
- UI-Live-Feed zeigt 0 Aktionen trotz real erzeugter Aktionen (Event-Bus).
