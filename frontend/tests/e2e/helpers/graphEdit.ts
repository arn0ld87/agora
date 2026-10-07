import { expect, type Page } from '@playwright/test';

/**
 * Graph-Leser mit Bearbeitungsspalte — Herkunfts- und Sperr-Gate (Etappe 8, #1808, ADR-0022).
 *
 * Drei Eigenschaften, die das Gate sichert, weil sie nicht aus dem Aussehen
 * folgen:
 *
 * 1. Die Herkunftsmarke ist **Text plus Symbol**, nie nur Farbe. Eine nur
 *    farblich erkennbare Marke ist für Farbfehlsichtige nicht vorhanden und im
 *    Ausdruck identisch mit einer extrahierten Kante.
 * 2. Der Sperrzustand ist sichtbar und **nennt den Ausweg** — als Bedienelement,
 *    nicht als Wort in einem Nebensatz.
 * 3. Die Herkunft steht **am Element** und ist ablesbar: sie hängt an der Zeile
 *    des Elements, nicht in einer Legende irgendwo daneben.
 */

/** Ein Knoten von Hand, einer extrahiert; eine Kante bearbeitet, eine extrahiert. */
export interface OriginFixture {
  graph_id: string;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

const NODE_MANUAL = '44444444-4444-4444-8444-444444444444';
const NODE_ORGANISATION = '22222222-2222-4222-8222-222222222222';
const NODE_TOWN = '33333333-3333-4333-8333-333333333333';
const EDGE_MANUAL = '55555555-5555-4555-8555-555555555555';
const EDGE_EXTRACTED = '66666666-6666-4666-8666-666666666666';

export const ORIGIN_FIXTURE_NODE_IDS = {
  manual: NODE_MANUAL,
  extracted: NODE_ORGANISATION,
  town: NODE_TOWN,
} as const;

export const ORIGIN_FIXTURE_EDGE_IDS = {
  manual: EDGE_MANUAL,
  extracted: EDGE_EXTRACTED,
} as const;

/**
 * Graph mit einer Handänderung. `graph_id` muss die echte sein: die Sperre wird
 * gegen den Bestand geprüft, ein erfundener Graphen lieferte `404` statt des
 * erwarteten gesperrten Zustands.
 */
export function originFixture(graphId: string): OriginFixture {
  return {
    graph_id: graphId,
    nodes: [
      {
        uuid: NODE_MANUAL,
        name: 'Neues Buero',
        labels: ['Organisation'],
        entity_type: 'Organisation',
        summary: 'von Hand angelegt',
        created_at: '2026-10-07T09:00:00',
        provenance: { origin: 'manual', changed_at: '2026-10-07T09:00:00', episode_count: 0 },
      },
      {
        uuid: NODE_ORGANISATION,
        name: 'Kreistag',
        labels: ['Organisation'],
        entity_type: 'Organisation',
        summary: 'Beschlussgremium des Landkreises',
        created_at: '2026-10-01',
        provenance: { origin: null, episode_count: 2 },
      },
      {
        uuid: NODE_TOWN,
        name: 'Moorhagen',
        labels: ['Ort'],
        entity_type: 'Ort',
        created_at: null,
        provenance: { origin: null, episode_count: 0 },
      },
    ],
    edges: [
      {
        uuid: EDGE_MANUAL,
        name: 'ARBEITET_IN',
        fact: 'Von Hand erfasst, danach im Text geaendert.',
        source_node_uuid: NODE_MANUAL,
        target_node_uuid: NODE_TOWN,
        episode_ids: ['ep1'],
        created_at: '2026-10-01',
        provenance: { origin: 'edited', changed_at: '2026-10-07T10:00:00', episode_count: 1 },
      },
      {
        uuid: EDGE_EXTRACTED,
        name: 'TRIFFT_ENTSCHEIDUNG_UEBER',
        fact: 'Der Kreistag entscheidet ueber Moorhagen.',
        source_node_uuid: NODE_ORGANISATION,
        target_node_uuid: NODE_TOWN,
        episode_ids: ['ep1', 'ep2'],
        created_at: '2026-10-01',
        provenance: { origin: null, episode_count: 2 },
      },
    ],
  };
}

/**
 * Legt einen Graphen mit Herkunftsmerkmalen in die Antwort von
 * `GET /api/graph/data/<graph_id>`.
 *
 * Warum ueberhaupt? Der Build im Stub-Modus liefert `node_count=0` — der
 * deterministische NER gibt eine leere Entity-Liste zurueck (siehe
 * `upload-graph.spec.ts`), und die Stub-Ontologie hat keine Entity-Typen, mit
 * denen sich ueber `POST /api/graph/<id>/entities` eine Handentitaet anlegen
 * liesse (`_require_ontology_type` lehnt sie ab). Ohne diese Attrappe gaebe es
 * im Gate keine einzige Herkunftsmarke und es pruefte nichts.
 *
 * Nur die *Lesedaten* werden ersetzt. Projekt, Sperrzustand und alle anderen
 * Endpunkte kommen unveraendert aus dem Stack — der Sperrzustand, den das Gate
 * prueft, ist also ein echter.
 */
export async function stubGraphDataWithOrigin(page: Page, graphId: string): Promise<void> {
  await page.route('**/api/graph/data/**', async (route) => {
    const url = route.request().url();
    // Nur der angeforderte Graphen; ein fremder bleibt unangetastet.
    if (!url.includes(graphId)) return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: originFixture(graphId) }),
    });
  });
}

/** Das Symbol der Marke (`aria-hidden`, Dekoration) — nie der Bedeutungstraeger. */
async function symbolOf(page: Page, markSelector: string): Promise<string> {
  return page.locator(markSelector).locator('[aria-hidden="true"]').first().innerText();
}

/**
 * Prueft, dass eine Herkunftsmarke Text **und** Symbol traegt und nicht nur aus
 * einer Hintergrundfarbe besteht.
 *
 * Geprueft wird je Marke:
 * - ein nicht-leerer sichtbarer Text (die Bedeutung),
 * - ein eigenes Symbol, das `aria-hidden` ist (die Form, fuer Farbfehlsichtige
 *   und im Ausdruck),
 * - die Marke selbst ist nicht `aria-hidden` — sonst waere der Text fuer einen
 *   Screenreader weg und nur die Farbe bliebe.
 */
export async function assertOriginMarkIsTextPlusSymbol(
  page: Page,
  markSelector: string,
  expectedText: string,
): Promise<void> {
  const mark = page.locator(markSelector).first();
  await expect(mark, `Herkunftsmarke ${markSelector} fehlt`).toBeVisible();

  const text = (await mark.innerText()).trim();
  expect(text.length, `Herkunftsmarke ${markSelector} traegt keinen lesbaren Text`).toBeGreaterThan(0);
  expect(text.toLocaleLowerCase('de')).toContain(expectedText.toLocaleLowerCase('de'));

  const symbol = (await symbolOf(page, markSelector)).trim();
  expect(symbol.length, `Herkunftsmarke ${markSelector} traegt kein Symbol neben dem Text`).toBeGreaterThan(0);

  // Nicht nur Farbe: der Text muss auch ohne Farbe etwas sagen. Geprueft wird
  // das am Kontrast des Textes gegen den Hintergrund der Marke — faellt der
  // Text unsichtbar zurueck, traegt die Marke faktisch nur ihre Farbe.
  const contrast = await mark.evaluate((node) => {
    const style = window.getComputedStyle(node);
    return { color: style.color, background: style.backgroundColor, opacity: style.opacity };
  });
  expect(contrast.opacity).not.toBe('0');
  expect(contrast.color).not.toBe('rgba(0, 0, 0, 0)');
  expect(contrast.background).not.toBe(contrast.color);
}

/**
 * Prueft, dass die Herkunft am Element steht: in der Listenzeile des Elements
 * und in der Tabellenzeile, jeweils im Kopf derselben Zeile.
 */
export async function assertOriginStandsAtElement(
  page: Page,
  options: {
    /** Handentitaet bzw. Handkante. */
    id: string;
    /** Zugehoer des extrahierten Elements, das *keine* Handmarke tragen darf. */
    counterpartId: string;
    kind: 'entity' | 'edge';
    markTestId: string;
  },
): Promise<void> {
  const rowSelector = options.kind === 'entity' ? '[data-entity-id="' : 'tr[data-edge-id="';
  const attr = options.kind === 'entity' ? 'data-entity-id' : 'data-edge-id';

  // Liste bzw. Tabelle: die Marke haengt an der Zeile des Elements, nicht in
  // einer Legende daneben.
  const own = page.locator(`${rowSelector}${options.id}"]`);
  await expect(
    own.locator(`[data-testid="${options.markTestId}"]`),
    `Herkunftsmarke steht nicht an ${attr}="${options.id}"`,
  ).toHaveCount(1);

  // Das extrahierte Element traegt keine Handmarke. Sonst waere die Marke
  // konstant und damit nicht aussagekraeftig — genau die Verwechslung, die
  // ADR-0022 §5 verhindern will.
  await expect(
    page.locator(`${rowSelector}${options.counterpartId}"] [data-testid="${options.markTestId}"]`),
  ).toHaveCount(0);
}
