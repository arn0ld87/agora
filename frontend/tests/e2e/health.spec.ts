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
    await page.goto('/');
    // App-Mount-Anker: <div id="app"> in frontend/index.html (Zeile 27).
    // Vue mounted in main.ts via app.mount('#app').
    await expect(page.locator('#app')).toBeVisible();
    expect(errors, `Page errors: ${errors.join(', ')}`).toHaveLength(0);
  });

  test('4 · /api/status returns 200 with auth_mode single_user_token', async ({ baseURL }) => {
    const ctx = await request.newContext({ extraHTTPHeaders: authHeader() });
    const res = await ctx.get(`${baseURL}/api/status`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.auth_mode).toBe('single_user_token');
    await ctx.dispose();
  });
});
