# Sub-Slice 43 — Wording-Sync „Entitäten/Beziehungen/Attribute" + Hybrid-Tagline + Tool-Call-USP

**Datum:** 2026-05-05  
**Branch:** `feat/wording-sync-entities-relationships-attributes`

## Ziel

Frontend-Vokabular und README angleichen auf drei Dimensionen:

1. Begriffsmapping (User-Entscheidung, verbindlich)
2. Hybrid-Branding statt local-first
3. Tool-Call-USP als Differenzierungsmerkmal sichtbar machen

## Mapping-Tabelle

| Kontext | Alt (DE) | Neu (DE) | Alt (EN) | Neu (EN) |
|---|---|---|---|---|
| Graph-Knoten | Knoten | Entitäten | Nodes | Entities |
| Graph-Kanten | Kanten | Beziehungen | Edges | Relationships |
| Ontologie-Typen | Entitätstypen | Attribute | entity types | attributes |
| Statistik-Label | ΔKnoten | ΔEntitäten | ΔNodes | ΔEntities |
| Statistik-Label | ΔKanten | ΔBeziehungen | ΔEdges | ΔRelationships |
| Tagline | Schwarmintelligenz, lokal. | Schwarmintelligenz — lokal oder Cloud. | Swarm intelligence, local. | Swarm intelligence — local or cloud. |
| Footer-Credit | Agora — Schwarmintelligenz lokal. | Agora — Schwarmintelligenz, lokal oder Cloud. | Agora — Swarm intelligence, local. | Agora — Swarm intelligence, local or cloud. |
| Lead | „Vollständig lokal. Dein Laptop, dein Neo4j, dein Ollama." | „Lokal mit Ollama oder via Cloud-Endpoint — du entscheidest." | „Fully local. Your laptop, your Neo4j, your Ollama." | „Local with Ollama or via cloud endpoint — your choice." |

## Semantischer Hinweis (für spätere Reviews)

„Attribut" ist semantisch nicht synonym mit „Entitätstyp":
- **Entitätstyp** ist ein Klassifikator (z. B. Person, Organisation, Ort).
- **Attribut** ist eine Eigenschaft einer Entität (z. B. Name, Alter, Beruf).

Die Umbenennung folgt einer expliziten User-Entscheidung und ist als solche dokumentiert. Bei zukünftigen Ontologie-UI-Erweiterungen sollte geprüft werden, ob die neue Terminologie für neue Nutzer verständlich ist.

## Liste geänderter Dateien

1. `frontend/src/i18n/locales/de.json` — Begriffe, Tagline, Lead, Step-03-desc, Footer-Credit, Step3.sub, `home.differentiators`
2. `frontend/src/i18n/locales/en.json` — Spiegelung aller DE-Änderungen
3. `frontend/src/contracts/graphDiffContract.ts` — Validierungsmeldungen Z. 111 + 128
4. `frontend/src/components/graph/__tests__/GraphDiffPanel.spec.ts` — i18n-Mocks Z. 49–50 + Assertions Z. 181–182
5. `frontend/src/composables/useGraphRender.ts` — Kommentar Z. 333
6. `README.md` — DE-Sektion Z. 77, 81, 97, 112
7. `frontend/src/views/Home.vue` — `differentiators` computed + Render-Block + Scoped CSS

## rg-Verifikationsbelege

### Begriffe in i18n + Code (nach Änderung)

```
rg -n "Knoten|Kanten|Entitätstyp" frontend/src/i18n/ frontend/src/contracts/ frontend/src/components/graph/__tests__/ frontend/src/composables/useGraphRender.ts
→ (leer)
```

### README begriffsfrei

```
rg -n "Knoten|Kanten|Entitätstyp|entity type|entity-type" README.md
→ (leer)
```

### Local-First-Tagline weg

```
rg -ni "vollständig lokal|Schwarmintelligenz, lokal\.|Schwarmintelligenz lokal\.|Fully local|Swarm intelligence, local\." frontend/src/i18n/
→ (leer)
```

### Tool-Call-USP-Key existiert + wird referenziert

```
rg -n "differentiators|toolCalls|tool.call" frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
→ de.json:132: "differentiators": [
→ en.json:121: "differentiators": [
→ en.json:124: "desc": "...they research online and query the knowledge graph..."
→ en.json:314: "sub": "...They don't hallucinate — instead they use tool calls..."

rg -n "differentiators" frontend/src/views/ frontend/src/components/
→ Home.vue:147: const differentiators = computed(() => tm('home.differentiators'))
→ Home.vue:250–253: Render-Block
→ Home.vue:586+: Scoped CSS
```

## Test-Output

```
Test Files  41 passed (41)
     Tests  427 passed (427)
  Duration  8.03s
```

`npm run check`: grün (vue-tsc, vitest coverage, vite build)  
Schema-Drift: leer
