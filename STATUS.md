# Agora — Operations-Status (Sync-Snapshot)

**Stand:** 2026-07-24
**Branch:** `chore/status-sync-2026-07-24`
**Geprüfte Baseline:** `98d8d596` (PR #858 auf `main`)

> **Hinweis:** Dieses Dokument ist ein **operativer Sync-Snapshot** für den aktuellen Stand laufender Arbeiten. Die kanonische Release-/Projekt-Status-SSoT bleibt [`docs/STATUS.md`](docs/STATUS.md) — diese Datei ersetzt sie nicht, sondern ergänzt sie um tagesaktuelle Operations-Punkte, die in den strukturierten Release-Status nicht passen.

## Container

- `agora`: **up**, **healthy** (Compose-Stack produktiv gestartet, Healthcheck passiert).

## Bekannte Issues

- **Keine offenen OOM-Vorfälle** nach Anwendung des TWHIN-BERT-fp16-Memory-Profils (PR #859, Commit `99fd1c43`). Vorbehaltlich der noch ausstehenden Container-Smoke-Run-Validierung mit `AGORA_DEBUG_MEMORY=1` (Handoff an Folgeschritt). Bis dahin gilt: grüne Unit- und Help-Smoke-Tests, aber kein realer Sim-Lauf gegen das 2.8-GiB-Limit unter Beobachtung.

## Offene Punkte

- **Frontend-Fixes laufen** (Vue-v4-Konsolidierung, Issue #760; Umsetzungskarte [#829](https://github.com/arn0ld87/agora/issues/829)) — parallele Branches aktiv, kein Eingriff in dieser Sync-Slice nötig.
- **OpenAI-Key-Rotation** — User-Aktion ausstehend. Der bestehende `LLM_API_KEY` muss an der Provider-Connection rotiert werden, sobald die Rotation extern angestoßen ist. Bis dahin läuft der Provider-Key-Guard weiterhin gegen den aktuellen Key; ein fehlgeschlagener Auth-Check liefert die reguläre 422 mit Handlungsanweisung.

## Sync-Aktionen in diesem Branch

- `CHANGELOG.md` um drei `Unreleased`-Einträge ergänzt: PR #859 (TWHIN-BERT fp16), PR #860 (Gemini `/v1beta/openai`), PR #861 (`SAFE_ENV_KEYS` für `REDIS_URL` + `HF_TOKEN`).
- Diese `STATUS.md` neu angelegt (siehe Hinweis oben zur Abgrenzung von `docs/STATUS.md`).
- Kein Push vorgesehen — lokaler Commit reicht für den Sync-Snapshot.
