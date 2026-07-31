import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

function repoRootPath(): string {
  if (process.env.GITHUB_WORKSPACE) {
    return process.env.GITHUB_WORKSPACE;
  }
  return resolve(process.cwd(), '..');
}

/**
 * Gibt Container-Logs auf stdout aus, damit sie im CI-Log landen.
 *
 * Wird immer ausgeführt wenn process.env.CI gesetzt ist.
 * Im Erfolgsfall erzeugt dies wenig Lärm (Logs sind kurz bei grünem Stack).
 * Im Fehlerfall liefert es die Backend-Exception, die sonst unsichtbar wäre
 * (CI zeigt nur den Playwright-Fehler, nicht den Container-Traceback).
 *
 * Compose-Befehl muss identisch mit e2e-down.sh / e2e-up.sh sein. Seit Issue
 * #989 ist das keine Absichtserklärung mehr, sondern strukturell erzwungen:
 * scripts/e2e-compose.sh hält Dateiliste und Projektnamen an genau einer
 * Stelle. Vorher lief die Kette auseinander — e2e-down.sh lud das
 * E2E-Override nicht mit und ließ `mock-models` als Orphan zurück.
 */
function dumpContainerLogs(repoRoot: string): void {
  const composeCmd = `bash "${resolve(repoRoot, 'scripts', 'e2e-compose.sh')}"`;

  // Compose-SERVICE-Namen (docker-compose.yml), nicht Container-Namen: `docker
  // compose logs <name>` erwartet den Service-Key. Mit den Container-Namen
  // (agora-e2e-neo4j/agora-e2e-redis) lieferte der Aufruf im CI-Fehlerfall
  // leere Logs.
  const services: Array<{ name: string; tail: number }> = [
    { name: 'agora', tail: 500 },
    { name: 'neo4j', tail: 200 },
    { name: 'redis', tail: 100 },
  ];

  console.log('\n========== [e2e-globalTeardown] CONTAINER LOGS ==========');
  for (const { name, tail } of services) {
    console.log(`\n---------- ${name} (tail=${tail}) ----------`);
    try {
      execSync(`${composeCmd} logs ${name} --tail=${tail} 2>&1`, {
        stdio: 'inherit',
        cwd: repoRoot,
        // 30 s Timeout pro Service — sollte immer reichen
        timeout: 30_000,
      });
    } catch (err) {
      // Service evtl. nicht gestartet (z. B. bei frühem Stack-Fehler) oder
      // Container bereits heruntergefahren — non-fatal, Status loggen statt Trace.
      const message = err instanceof Error ? err.message : String(err);
      console.log(
        `[e2e-globalTeardown] logs ${name} not available (container down or not started): ${message}`,
      );
    }
  }
  console.log('\n========== [e2e-globalTeardown] END CONTAINER LOGS ==========\n');
}

export default async function globalTeardown() {
  if (process.env.AGORA_E2E_SKIP_STACK === 'true') {
    return;
  }
  const repoRoot = repoRootPath();

  // Container-Logs dumpen bevor der Stack heruntergefahren wird.
  // Bedingung: CI-Umgebung (process.env.CI gesetzt, z. B. auf GitHub Actions).
  // Lokal ohne CI-Flag entfällt der Dump (kein unnötiger Lärm).
  if (process.env.CI) {
    dumpContainerLogs(repoRoot);
  }

  const script = resolve(repoRoot, 'scripts', 'e2e-down.sh');
  console.log(`[e2e-globalTeardown] running ${script}`);
  try {
    execSync(`bash "${script}"`, { stdio: 'inherit', cwd: repoRoot });
  } catch (err) {
    console.error('[e2e-globalTeardown] non-fatal teardown error:', err);
  }
}
