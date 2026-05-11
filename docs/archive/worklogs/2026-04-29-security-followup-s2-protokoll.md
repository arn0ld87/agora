# Arbeitsprotokoll — Security-Followup S2

**Datum:** 2026-04-29 (Europe/Berlin)
**Slice:** S2 — `?token=` Hard-Removal
**Plan:** [`docs/2026-04-29-security-followup-plan.md`](./2026-04-29-security-followup-plan.md)
**Status:** **Vertagt.**

## Begründung

Plan-Vorgabe für S2:

> Telemetrie aus dem Deprecation-Pfad bestätigt: kein Live-Setup nutzt `?token=` mehr. Logger-Warning aus `auth.py:54-59` muss seit ≥2 Wochen leise sein. Falls Telemetrie noch nicht ausgewertet — diesen Slice **vertagen**, nicht raten.

Der Deprecation-Pfad (Logger-Warning) wurde im selben Sprint eingeführt:

- `92cfdf9 chore(security): clarify auth-mode logging for anonymous opt-in` — 2026-04-29
- `201c0a0 feat(security): /api/auth/ticket and ticket-aware request auth` — 2026-04-29
- `0b940ab feat(security): frontend uses signed tickets for SSE` — 2026-04-29

Das Telemetrie-Fenster von ≥2 Wochen ist nicht erfüllt. Hard-Removal jetzt würde Drittclients brechen, die noch nicht migriert sind (z. B. eigene Skripte, Remote-Abrufer, Tailnet-Tools mit altem `?token=`-Pattern). Plan-Logik schlägt explizit Vertagen vor.

## Wiederaufnahme-Bedingung

S2 wird neu eingeplant, sobald:

1. Backend-Logs aus mindestens zwei Wochen Live-Betrieb gegen den Logger-Output `auth: ?token= query fallback used on …` geprüft sind.
2. Keine Treffer für externe Clients (frontend nutzt Tickets, eigener Backend-Code nutzt Header).
3. Falls Treffer: vorher die Caller-Migration anstoßen.

## Status

**Vertagt — kein Code-Change in diesem Sprint.** S1 und S3 laufen unabhängig.
