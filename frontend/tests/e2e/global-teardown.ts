import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

function repoRootPath(): string {
  if (process.env.GITHUB_WORKSPACE) {
    return process.env.GITHUB_WORKSPACE;
  }
  return resolve(process.cwd(), '..');
}

export default async function globalTeardown() {
  if (process.env.AGORA_E2E_SKIP_STACK === 'true') {
    return;
  }
  const repoRoot = repoRootPath();
  const script = resolve(repoRoot, 'scripts', 'e2e-down.sh');
  console.log(`[e2e-globalTeardown] running ${script}`);
  try {
    execSync(`bash "${script}"`, { stdio: 'inherit', cwd: repoRoot });
  } catch (err) {
    console.error('[e2e-globalTeardown] non-fatal teardown error:', err);
  }
}
