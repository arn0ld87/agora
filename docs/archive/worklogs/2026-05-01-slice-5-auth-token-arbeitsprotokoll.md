# Slice 5 — Frontend-Token-Haertung + Auth-Doku (PR5)

**Datum:** 2026-05-01
**Branch:** `claude/sleepy-torvalds-32f68f`
**Slice-Quelle:** Repo-Review PR5 (User-Prompt, „Frontend-Token-Haertung + Auth-Doku").

## Ziel

Frontend-Token darf nicht blind in `localStorage` persistieren. Memory-Mode
als Prod-Haertung bereitstellen. Auth-Vertrag dokumentieren.

## Ausgangslage

- [frontend/src/api/index.js:16–19](../frontend/src/api/index.js:16) las den
  Token unbedingt aus `localStorage`. Kein Memory-Mode, kein Switch.
- XSS-Sanitizer in [frontend/src/utils/markdown.js](../frontend/src/utils/markdown.js)
  und 9 Tests in
  [frontend/src/utils/__tests__/markdown.spec.js](../frontend/src/utils/__tests__/markdown.spec.js)
  waren bereits vorhanden — Slice 5 fuegt hier **keine** Duplikate hinzu.

## Aenderungen

### frontend/src/api/index.js
- Modul-Variable `_memoryToken` fuer Memory-Mode.
- `setAgoraToken(token)`: Schreibt in `_memoryToken` (Memory-Mode) oder
  `localStorage` (Default/Dev).
- `getAgoraToken()`: Waehlt zwischen Memory-Mode (`VITE_AGORA_TOKEN_STORAGE`
  === `"memory"`) und `localStorage`-Fallback. Kommentare markieren
  localStorage als bewussten Dev-Fallback.

### docs/auth.md (neu)
- Token-Header-Vertrag (`X-Agora-Token`, `Authorization: Bearer`).
- Ticket-Flow (SSE/Download-Auth via signed single-use tickets).
- Query-Token-Deprecation (`?token=` → Warning).
- Storage-Vergleich: localStorage (Dev), Memory (Prod), HttpOnly-Cookie
  (Zielarchitektur).
- Konfigurationstabelle pro Umgebung.

## Verifikation

- `npm run check` gruen
- Backend: 689 passed, 9 skipped
- Frontend: 40 passed, Lint 0 errors / 1 pre-existing Warnung
- Build ok

## Offene Punkte

- HttpOnly-Cookie-Session-Backend ist **nicht** in diesem Slice implementiert;
  steht auf der Zielarchitektur-Roadmap.
