# Slice K.1 — OpenAI-Embedding-Switch dokumentieren

**Datum:** 2026-05-04
**Trigger:** User-Auftrag „Stell im nächsten Schritt das embedding auf
openai um (text-embedding-3-small)".
**Foundation:** Commit `a191d09` (`feat(embeddings): support
openai-compatible embedding endpoints`) — war lokal angelegt aber NICHT
auf `origin/main` gepusht. Wurde im Rahmen dieses Slices via
`git cherry-pick a191d09` mitgenommen. Gemini-Code-Assist (HIGH-Catch
auf erstem Doku-only-Push) hat den Foundation-Gap aufgedeckt.

## Entscheidung

**Kein Code-Default-Wechsel.** Agora bleibt Local-first laut
User-Profil (Ollama als Default). Der Switch passiert ausschließlich über
`.env` — der Code unterstützt beide Provider seit `a191d09` ohne weitere
Änderungen.

User-Bestätigung explizit: „ja zu deiner frage wir hauen es erstmal in
die .env".

## Files geändert

- `.env.example` — neuer kommentierter Block mit OpenAI-Beispiel-Zeilen
  (`EMBEDDING_BASE_URL=https://api.openai.com/v1`,
  `EMBEDDING_MODEL=text-embedding-3-small`, `EMBEDDING_API_KEY=sk-...`,
  `VECTOR_DIM=1536`) + Hinweis auf andere OpenAI-Modelle (`-3-large`,
  `ada-002`). Kein echter Key im Repo.
- `docu/embedding-provider-switch.md` — neue Anleitung Ollama ↔ OpenAI
  mit Drop-Snippet für Neo4j-Vector-Indexe, Verifikations-One-Liner und
  Kosten-/Latenz-Caveat.
- `CHANGELOG.md` — `[Unreleased] ### Changed`-Eintrag.

## Lokale Umstellung beim User

Der User setzt selbst die 4 Zeilen in seine lokale `.env` (Sandbox
blockiert `.env`-Reads — saubere Secret-Handling-Voreinstellung). Vector-
Index-Drop in Neo4j wurde freigegeben („daten in neo4j sind egal, kann
weg"); beim nächsten Sim-Start wird der Index automatisch mit
`VECTOR_DIM=1536` neu angelegt.

## Tests

Keine neuen Tests nötig — der Foundation-Slice `a191d09` deckt den
Provider-Switch bereits in `tests/test_embedding_service.py` ab (Mock
auf `requests.post`-Response). Reine Doku-/`.env.example`-Änderung.

## Risiken

- Kein API-Key im Repo — wird in der lokalen `.env` des Users gehalten.
- Kosten: `text-embedding-3-small` ~5× günstiger als `-3-large`.
  Persona-Generierung mit ~200 Personas × ~500 Tokens entspricht ~$0.002
  pro Lauf — vernachlässigbar.
- Latenz: 100–300 ms Round-Trip pro Batch — relevant nur bei sehr großen
  Persona-Generierungen.

## Followup-Möglichkeiten (nicht in diesem Slice)

1. **Re-Embedding-Skript** für bestehende Knoten beim Provider-Wechsel
   (statt Drop). Wäre eigener M-Slice mit Rate-Limiting + Backfill.
2. **Provider-Probe im Health-Endpoint** anzeigen (Provider + Modell +
   Dimension), damit Users im Frontend sehen, welcher Embedding-Pfad
   aktiv ist. Hängt an Slice E (Live-Modell-Anzeige im Header).
