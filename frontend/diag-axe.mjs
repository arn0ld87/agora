import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const BASE = 'http://127.0.0.1:8280';
const TOKEN = process.env.AGORA_AUTH_TOKEN || 'e2e-test-token-fixed-for-ci';

const routes = [
  '/dashboard',
  '/runs',
  '/settings/general',
  '/settings/integrations',
  '/settings/profile',
  '/settings/api-keys',
  '/settings/llm-providers',
  '/settings/embedding',
  '/onboarding',
];

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL: BASE });
  await context.addInitScript(([k, v]) => {
    window.localStorage.setItem(k, v);
  }, ['agora_token', TOKEN]);
  const page = await context.newPage();

  // Dismiss onboarding first
  const dismissRes = await page.request.post(`${BASE}/api/onboarding/dismiss`, {
    headers: { 'X-Agora-Token': TOKEN },
  });
  console.log('dismiss status', dismissRes.status());

  for (const route of routes) {
    await page.goto(route, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);
    const results = await new AxeBuilder({ page }).analyze();
    const violations = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    console.log(`\n=== ${route} (${violations.length} violation types) ===`);
    for (const v of violations) {
      console.log(`[${v.impact}] ${v.id}: ${v.description}`);
      for (const node of v.nodes.slice(0, 8)) {
        console.log('  target:', JSON.stringify(node.target));
        console.log('  html:', node.html.slice(0, 200));
        if (node.any && node.any[0] && node.any[0].data) {
          console.log('  data:', JSON.stringify(node.any[0].data));
        }
        console.log('  failureSummary:', node.failureSummary);
      }
    }
  }

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
