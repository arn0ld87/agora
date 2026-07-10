# Provider-Matrix

Stand: 2026-07-10. „Geplant“ bedeutet nicht implementiert.

| Eintrag | Transport | Auth | Discovery | Chat | Embeddings | Bridge-Entscheid |
|---|---|---|---|---|---|---|
| OpenAI API | OpenAI HTTP | API-Key | `/v1/models` | ja | ja | normale API |
| Anthropic API | Anthropic HTTP | API-Key/WIF | `/v1/models` | ja | nein | normale API |
| Gemini API | Gemini HTTP | API-Key, optional OAuth | Models API | ja | ja | normale API |
| MiniMax API | Anthropic-/anbieterkompatibles HTTP | API-Key | anbieterspezifisch | ja | nicht zugesagt | normale API |
| OpenCode Go | OpenAI-kompatibles HTTP | Go-API-Key | `/v1/models` | ja | nicht zugesagt | normale API |
| Ollama lokal | Ollama HTTP | keine lokale Auth | `/api/tags` | modellabhängig | ja | lokaler Dienst |
| Ollama Cloud direkt | Ollama HTTP | API-Key | Cloud-Katalog | ja | modellabhängig | normale API |
| Benutzerdefiniert | OpenAI-kompatibles HTTP | none/API-Key | optional | capability-probed | capability-probed | normale API |
| Codex CLI | lokaler Prozess | offizieller Codex-Login | CLI | ja | nein | nur lokaler Security-Spike |
| Claude Code CLI | lokaler Prozess | offizieller Claude-Code-Login | CLI | ja | nein | nur lokaler Security-Spike |

## Capability-Vertrag

Modelle werden nicht aus Namen erraten. `AiModel` soll mindestens enthalten:

```text
chat, embeddings, streaming, tool_calling, json_object, json_schema,
vision, reasoning, context_window, max_output_tokens,
embedding_dimensions, local_or_cloud, deprecated,
source: live | cached | fallback | custom
```

Live-Metadaten gewinnen. Cache und Fallback müssen sichtbar markiert sein.
Unbekannte Fähigkeiten sind `unknown`, nicht implizit `true`.

## Subscription-Bridges

Offizielle Codex- und Claude-Code-Dokumentation bestätigt lokale Anmeldung und
nichtinteraktive Befehle. Das ist noch keine Freigabe für einen Serveradapter.
Ein späterer Spike muss mindestens prüfen:

- zulässige Nutzungsbedingungen und Plan-Grenzen;
- direkte Argumentlisten ohne Shell;
- minimales Environment, begrenztes Arbeitsverzeichnis, Timeout und Abbruch;
- lokale Aktivierung, Docker/VPS standardmäßig aus;
- keine Auth-Dateien, Cookies, Keychain- oder OAuth-Token-Auslese;
- Output-Limit, Concurrency-Limit und Audit ohne Prompt-/Secret-Leak.
