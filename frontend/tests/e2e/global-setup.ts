import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

export default async function globalSetup() {
  if (process.env.AGORA_E2E_SKIP_STACK === 'true') {
    console.log('[e2e-globalSetup] AGORA_E2E_SKIP_STACK=true — assuming stack is already up');
    return;
  }
  const repoRoot = resolve(__dirname, '..', '..', '..');
  const script = resolve(repoRoot, 'scripts', 'e2e-up.sh');
  console.log(`[e2e-globalSetup] running ${script}`);
  execSync(`bash "${script}"`, { stdio: 'inherit', cwd: repoRoot });
}
