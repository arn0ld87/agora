# Observability Slice 4 — SLOs + Burn-Rate-Alerts

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` oder `superpowers:executing-plans`.

**Status:** Plan, Implementation offen. Setzt Slice 1 + 2 + 3 voraus.

**Goal:** Vier SLOs (Service Level Objectives) für Agora definiert, mit Burn-Rate-Alerts in SigNoz Alertmanager. Wenn ein SLO innerhalb von 5 min mit ≥ 14.4× Burn-Rate verletzt wird, schickt SigNoz einen Alert (lokal: Webhook → Notification; mittelfristig: Slack/Telegram).

**Architecture:** SigNoz-Alertmanager (bereits in `docker-compose.observability.yml` aus Slice 1a). Alert-Rules werden als YAML versioniert. Zwei Burn-Rate-Fenster: kurz (5 min, 14.4×) und lang (1 h, 6×) — Multi-Window-Multi-Burnrate nach Google-SRE-Workbook.

**Tech Stack:** SigNoz Alertmanager + YAML-Rules, keine neuen Python-Deps. Optional: `signoz-cli` für Rules-Sync, falls man API benutzen will.

**Aufwand:** ~2 Tage in 2 Sub-Slices.

---

## SLOs (Definitionen)

| SLO | Indicator | Objective | Datenquelle |
|---|---|---|---|
| Sim-Erfolgsrate | 1 - (rate(agora_sim_started{status="failed"}) / rate(agora_sim_started) or vector(0)) | ≥ 95 % über 7 Tage | Slice 2 Counter |
| Sim-Latenz p95 | `histogram_quantile(0.95, agora_sim_duration_seconds_bucket)` | ≤ 90 s (Stub-Mode 30 s) | Slice 2 Histogram |
| Backend-Verfügbarkeit | `1 - rate(http_server_duration_seconds_count{status_code=~"5.."}) / rate(http_server_duration_seconds_count)` | ≥ 99 % über 7 Tage | Flask-Auto-Instrumentation aus Slice 1b |
| Bus-Event-Loss | `rate(agora_bus_events_dropped_total)` | ≤ 0.1 events/s über 1 h | Slice 2 Counter |

---

## File Structure

### Neu
- `deploy/observability/alerts/sim-success-rate-slo.yaml`
- `deploy/observability/alerts/sim-latency-p95-slo.yaml`
- `deploy/observability/alerts/backend-availability-slo.yaml`
- `deploy/observability/alerts/bus-event-loss-slo.yaml`
- `docs/decisions/0003-observability-slos.md` — ADR mit Begründungen + Stakeholder-Kontext.

### Modify
- `docker-compose.observability.yml` — Alert-Rules-Volume-Mount in `signoz-alertmanager`.
- `deploy/observability/README.md` — Abschnitt „Alerts und SLOs", Webhook-Setup-Hinweis.

---

## Task 1 — SLO-Rules + ADR

- [ ] ADR `0003-observability-slos.md` schreiben. Begründung pro SLO: warum dieser Objective-Wert, welcher Stakeholder hat ihn definiert, was passiert bei Verletzung.
- [ ] Vier Alert-Rule-YAMLs nach SigNoz-Schema (Promtool-kompatibel). Jeweils zwei Rules: `burnrate_5m_short` und `burnrate_1h_long`.
- [ ] Volume-Mount im `docker-compose.observability.yml` ergänzen.

## Task 2 — Webhook + Smoke + Worklog

- [ ] Lokaler Webhook-Receiver (`scripts/dev/alert-webhook.py` mit Flask, druckt eingehende Alerts auf stdout) als Smoke-Empfänger.
- [ ] Smoke: artificial Failure produzieren (z. B. Sim mit invalidem Provider triggern), 5 min warten, prüfen ob Burn-Rate-Alert feuert.
- [ ] Worklog + STATUS.md + `sync-status.sh` + Single PR.

---

## Akzeptanzkriterien

1. Vier YAML-Rules sind im Repo versioniert, Promtool-validiert.
2. SigNoz Alertmanager lädt die Rules ohne Parse-Errors (`docker logs signoz-alertmanager`).
3. Artificial Failure-Smoke erzeugt einen Burn-Rate-Alert binnen 5 min.
4. ADR-0003 dokumentiert die SLOs und Eskalationspfad.

---

## Risk Register

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme |
|---|---|---|
| Alert-Fatigue durch zu strenge Burn-Rate-Schwellen | Mittel | Multi-Window-Multi-Burnrate nach SRE-Workbook (kurz UND lang müssen feuern) |
| Webhook ohne Auth-Token | Hoch lokal, niedrig prod | Token-Anforderung notieren; host.docker.internal für lokale Tests nutzen |
| ClickHouse-Query-Last bei vielen Rules | Niedrig | Rule-Cardinality begrenzen, kein `simulation_id`-Label |

---

## Out of Scope

- Pager-Duty / On-Call-Schedule — Solo-Setup, manueller Slack/Telegram-Ping reicht.
- Anomaly-Detection — Slice 5 (möglicherweise mit lokalem LLM via Ollama).
- Long-Term-Retention von Metrics jenseits SigNoz-Default — kommt mit Production-Slice.
