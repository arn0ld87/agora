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

  test('3 · Frontend SPA mounts without console errors', async ({ page, context }) => {
    await injectAuthToken(context);
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/', { waitUntil: 'networkidle' });
    // App-Mount-Anker: <div id="app"> in frontend/index.html.
    // Vue mounted in main.ts via app.mount('#app'). Warten auf das erste
    // gerenderte Kind-Element — der äußere div hat in CI initial keine
    // intrinsische Höhe und schlägt toBeVisible() fehl, bevor Vue gemountet
    // hat. 15s Timeout für ressourcenarmes CI-Headless.
    await expect(page.locator('#app').locator(':scope > *').first()).toBeVisible({ timeout: 15000 });
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
