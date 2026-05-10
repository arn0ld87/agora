import { test, expect, request } from '@playwright/test';
import { injectAuthToken, authHeader } from './helpers/auth';

test.describe('M11.4a · Health-Smoke', () => {
  test('1 · Reverse-Proxy /healthz returns 200', async ({ baseURL }) => {
    const ctx = await request.newContext();
    const res = await ctx.get(`${baseURL}/healthz`);
    expect(res.status()).toBe(200);
    const body = await res.text();
    expect(body.trim()).toBe('ok');
    await ctx.dispose();
  });

  test('2 · App-Level /health returns 200', async ({ baseURL }) => {
    const ctx = await request.newContext();
    const res = await ctx.get(`${baseURL}/health`);
    expect(res.status()).toBe(200);
    await ctx.dispose();
  });

  test('3 · Frontend SPA loads without console errors', async ({ page, context }) => {
    await injectAuthToken(context);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    // M11.4b-Followup-3: 'domcontentloaded' statt 'networkidle'.
    // SPA-Root mit Pinia-Polling erreicht nie networkidle. 'domcontentloaded'
    // ist deterministisch; toHaveTitle(/Agora/) ist der Mount-Indikator.
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    // Smoke-Niveau: Document/Bundle laden, kein Page-Error. Strenger
    // Mount-Check (Vue rendert erstes Kind in #app) wurde rausgenommen,
    // weil App.vue in CI-Headless ohne live Backend-Daten nicht zuverlässig
    // sichtbaren Inhalt hat — separater Slice für volle Mount-Smokes
    // sobald M11.4b/c (Upload+Graph, Minimalreport) den Auth-/Daten-Flow
    // durchstellt.
    await expect(page).toHaveTitle(/Agora/);
    expect(errors, `Page errors: ${errors.join(', ')}`).toHaveLength(0);
  });

  test('4 · /api/status returns 200 with auth_mode single_user_token', async ({ baseURL }) => {
    const ctx = await request.newContext({ extraHTTPHeaders: authHeader() });
    const res = await ctx.get(`${baseURL}/api/status`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    // /api/status liefert backend.auth_mode (nested in json_success-Envelope),
    // siehe backend/app/api/status.py::_get_backend_status.
    expect(body.backend?.auth_mode).toBe('single_user_token');
    await ctx.dispose();
  });
});
