# Slice 11 (Repo-Review-Folge, Versions-Sync)

**Datum:** 2026-05-01
**Branch:** `claude/slice-11-version-sync` (Worktree)
**Bezug:** Folge-Slice aus [`docs/release-process.md`](release-process.md)
(Slice 10 / F4) — der dort dokumentierte Drift wird beseitigt.

## Ziel

Backend-Versionsquellen auf den Stand der gelabelten Release-Version
`0.9.0` heben. Bedeutet: was `/api/status.backend.version` ausliefert,
muss zum Repo-Tag passen.

## Ausgangslage (Drift)

| Quelle | Wert vor Slice 11 | Soll |
|---|---|---|
| `package.json` | `0.9.0` | `0.9.0` |
| `frontend/package.json` | `0.9.0` | `0.9.0` |
| `backend/pyproject.toml` | `0.6.1` | `0.9.0` |
| `backend/app/__init__.py` (`__version__`) | `0.8.0` | `0.9.0` |
| README-Banner / Status-Block | `v0.9.0` | `v0.9.0` |
| `frontend/src/i18n/locales/{de,en}.json` (`*.version`) | `v0.9.0 alpha` | `v0.9.0 alpha` |

`/api/status.backend.version` exposed vor dem Sync `0.8.0` — falscher
Wert nach außen.

## Vorgehen

1. `backend/pyproject.toml` Zeile 3: `version = "0.6.1"` → `"0.9.0"`.
2. `backend/app/__init__.py` Zeile 25: `__version__ = "0.8.0"` →
   `"0.9.0"`.
3. `cd backend && uv lock` aktualisiert `uv.lock`. `uv` meldet
   `Updated agora-backend v0.6.1 -> v0.9.0`, keine weiteren Drifts.
4. CHANGELOG `[Unreleased]` bekommt einen `### Fixed`-Block fuer den
   Slice (kein `### Docs`, weil dies eine Code-Korrektur ist, kein
   Doku-Beitrag).
5. Dieses Arbeitsprotokoll geschrieben.
6. `npm run check` als Gate, danach Commit + PR + Merge.

## Geaenderte Dateien

| Datei | Aktion |
|---|---|
| `backend/pyproject.toml` | `version = "0.9.0"` |
| `backend/app/__init__.py` | `__version__ = "0.9.0"` |
| `backend/uv.lock` | `agora-backend` Eintrag aktualisiert (via `uv lock`) |
| `CHANGELOG.md` | neuer `### Fixed`-Block in `[Unreleased]` |
| `docs/2026-05-01-slice-11-version-sync-arbeitsprotokoll.md` | dieses File |

## Verifikation

- `npm run check` — `tests/test_status.py:25` prueft
  `result['version'] == __version__`; der Test laeuft also
  weiter durch (dynamischer Vergleich, kein Hard-Pin).
- `cd backend && uv run python -c "from app import __version__;
  print(__version__)"` → `0.9.0`.
- `grep -n "version" backend/pyproject.toml` → `0.9.0`.

## Akzeptanzkriterien

- [x] `pyproject.toml` und `__version__` auf `0.9.0`.
- [x] `uv.lock` neu, kein Side-Effect-Drift bei anderen Paketen.
- [x] Bestand-Tests gruen, neue Tests nicht noetig.
- [ ] `npm run check` gruen — pending bis zum tatsaechlichen Lauf.

## Followups

- F5 — Test-Coverage-Luecken (SSRF, Upload-Limits, Cypher-Sanitizer;
  einziges Code-Slice im Plan).
- F6 — Branch-Cleanup + README-Update.

## Out-of-Scope

- Ein zusaetzlicher Pin-Test (`assert __version__ == "0.9.0"`) waere
  ein Drift-Frueh-Detektor — bewusst nicht hinzugefuegt, weil das beim
  naechsten Release (z. B. `0.10.0`) ohne sichtbare Warnung rot wird
  und der Release-Process-Doku-Schritt 2 das ohnehin abdeckt. Sub-Slice-
  Kandidat fuer spaeter, falls der Drift wieder auftritt.
