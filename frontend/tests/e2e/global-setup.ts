import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

// Repo-Root-Auflösung ohne __dirname (Playwright lädt TS als ESM, dort
// gibt es kein __dirname). GITHUB_WORKSPACE auf CI-Runnern, lokal Fallback
// über process.cwd() (Playwright läuft aus frontend/, ein Schritt rauf).
function repoRootPath(): string {
  if (process.env.GITHUB_WORKSPACE) {
    return process.env.GITHUB_WORKSPACE;
  }
  return resolve(process.cwd(), '..');
}

export default async function globalSetup() {
  if (process.env.AGORA_E2E_SKIP_STACK === 'true') {
    console.log('[e2e-globalSetup] AGORA_E2E_SKIP_STACK=true — assuming stack is already up');
    return;
  }
  const repoRoot = repoRootPath();
  const script = resolve(repoRoot, 'scripts', 'e2e-up.sh');
  console.log(`[e2e-globalSetup] running ${script}`);
  execSync(`bash "${script}"`, { stdio: 'inherit', cwd: repoRoot });
}
