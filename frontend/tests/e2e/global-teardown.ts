import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

export default async function globalTeardown() {
  if (process.env.AGORA_E2E_SKIP_STACK === 'true') {
    return;
  }
  const repoRoot = resolve(__dirname, '..', '..', '..');
  const script = resolve(repoRoot, 'scripts', 'e2e-down.sh');
  console.log(`[e2e-globalTeardown] running ${script}`);
  try {
    execSync(`bash "${script}"`, { stdio: 'inherit', cwd: repoRoot });
  } catch (err) {
    console.error('[e2e-globalTeardown] non-fatal teardown error:', err);
  }
}
