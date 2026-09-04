### Added (neuer LLM-Provider „Codex CLI (ChatGPT-Abo)“ — 2026-08-30)

- **Agora kann jetzt gegen die lokal eingeloggte Codex-CLI routen, statt einen `OPENAI_API_KEY` zu verlangen.** Der neue Provider `codex_cli` spricht `codex exec` als Subprozess in einem isolierten `cwd` und mit `--sandbox read-only` an — kein HTTP-Endpunkt, kein Secret im Store. Nutzung setzt eine bestehende, per ChatGPT-Abo authentifizierte Codex-CLI-Session voraus.
- Der Aufruf läuft mit hartem Timeout (Default 180s, konfigurierbar über `AGORA_CODEX_CLI_TIMEOUT_SECONDS`). Token-Streaming unterstützt dieser Provider in diesem Slice noch nicht.
- Bewusst nur Codex/ChatGPT in diesem Slice — ein möglicher Claude-CLI-Provider ist ausdrücklich nicht Teil dieser Änderung (höheres ToS-Risiko, eigenes Folge-Issue).
