import { test, expect, type Page, type Route } from '@playwright/test';
import { runAxe, assertNoCriticalViolations, check320pxNoHorizontalScroll } from './helpers/accessibility';

/**
 * #1617 · Supabase-Login gegen gemockte Endpunkte.
 *
 * Der Stack läuft im Legacy-Modus. Der Test schaltet den Browser per
 * page.route auf JWT: /api/auth/config meldet jwt_enabled, GoTrue unter
 * /__sb ist gemockt, ebenso /api/workspaces. Geprüft wird der Weg
 * Startseite → Login → Anmeldung → zurück, dass Agora-Aufrufe danach
 * `Authorization: Bearer` und `X-Agora-Workspace` tragen und nie
 * `X-Agora-Token`, sowie die A11y-Regeln der Login-View.
 */

const ACCESS_TOKEN = 'e2e-access-token';
const WORKSPACE_ID = 'aaaaaaaa-0000-4000-8000-00000000e2e1';

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function mockSupabase(page: Page, baseURL: string) {
  // Playwright prüft zuletzt registrierte Routen zuerst: der Catch-all für
  // übrige GoTrue-Pfade muss deshalb vor den spezifischen Routen stehen.
  await page.route('**/__sb/auth/v1/**', (route) => json(route, {}));
  await page.route('**/api/auth/config', (route) =>
    json(route, {
      success: true,
      data: {
        auth_backend: 'hybrid',
        jwt_enabled: true,
        supabase_url: `${baseURL}/__sb`,
        supabase_anon_key: 'e2e-anon-key',
      },
    }),
  );
  await page.route('**/__sb/auth/v1/token**', (route) => {
    const now = Math.floor(Date.now() / 1000);
    return json(route, {
      access_token: ACCESS_TOKEN,
      token_type: 'bearer',
      expires_in: 3600,
      expires_at: now + 3600,
      refresh_token: 'e2e-refresh-token',
      user: {
        id: '00000000-0000-4000-8000-00000000e2e0',
        aud: 'authenticated',
        role: 'authenticated',
        email: 'e2e@example.test',
        app_metadata: {},
        user_metadata: {},
        created_at: new Date().toISOString(),
      },
    });
  });
  await page.route('**/api/workspaces', (route) =>
    json(route, {
      success: true,
      data: [{ workspace_id: WORKSPACE_ID, name: 'E2E', slug: 'e2e', role: 'owner' }],
      count: 1,
    }),
  );
}

test.describe('#1617 · Supabase-Login (gemockt)', () => {
  test.beforeEach(async ({ page, baseURL }) => {
    await mockSupabase(page, baseURL ?? 'http://127.0.0.1');
  });

  test('1 · ohne Session landet jede Route auf dem Login', async ({ page }) => {
    await page.goto('/ablage', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/auth\/login\?next=(%2F|\/)ablage/);
    await expect(page.getByLabel(/E-Mail|Email/i)).toBeVisible();
  });

  test('2 · Anmeldung sendet danach Bearer und Workspace, nie den Master-Token', async ({ page }) => {
    const agoraHeaders: Record<string, string>[] = [];
    page.on('request', (req) => {
      const url = new URL(req.url());
      if (url.pathname.startsWith('/api/') && url.pathname !== '/api/auth/config') {
        agoraHeaders.push(req.headers());
      }
    });

    await page.goto('/auth/login?next=/ablage', { waitUntil: 'domcontentloaded' });
    await page.getByLabel(/E-Mail|Email/i).fill('e2e@example.test');
    await page.getByLabel(/Passwort|Password/i).fill('ein-langes-passwort');
    await page.getByRole('button', { name: /anmelden|sign in/i }).click();

    await expect(page).toHaveURL(/\/ablage/);
    const bearer = () => agoraHeaders.filter((h) => h['authorization'] === `Bearer ${ACCESS_TOKEN}`);
    await expect.poll(() => bearer().length).toBeGreaterThan(0);
    const withBearer = bearer();
    expect(withBearer.some((h) => h['x-agora-workspace'] === WORKSPACE_ID)).toBe(true);
    expect(agoraHeaders.every((h) => !('x-agora-token' in h))).toBe(true);
  });

  test('3 · Login-View erfüllt die Golden-Gate-Regeln', async ({ page }) => {
    await page.goto('/auth/login', { waitUntil: 'domcontentloaded' });
    await expect(page.getByLabel(/E-Mail|Email/i)).toBeVisible();
    assertNoCriticalViolations(await runAxe(page));
    await check320pxNoHorizontalScroll(page);
  });
});
