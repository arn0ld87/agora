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

// Slice 5.6: Seeded zwei Provider-Connections, gegen die der AiModelPicker
// im E2E-Stack live discovered:
//   - openai_compatible (online)  → http://mock-models      (liefert 2 Modelle)
//   - openai            (offline) → nicht auflösbarer DNS-Name (Probe schlägt fehl)
//
// connection_id MUSS == provider_kind sein (upsert_provider_connection
// validiert das). Zwei distinct kinds → zwei distinct Connections. Der
// Backend-Validator `_validate_public_base_url` lehnt localhost ab,
// erlaubt aber DNS-Namen — deshalb der Service-Name statt 127.0.0.1.
//
// api_key ist ein offensichtlicher Platzhalter (kein Secret-Wert); der
// openai_compatible-Adapter braucht einen non-empty Bearer-Header.
// baseUrl ist konfigurierbar via AGORA_E2E_MOCK_MODELS_BASE —
// Default `http://mock-models` (Compose-DNS im E2E-Stack), per Env
// ueberschreibbar fuer lokale Dev-Stacks ohne mock-models-Service
// (z.B. http://host.docker.internal:8081 hinter einem Host-seitigen
// `nginx:alpine` mit der deploy/e2e/mock-models/nginx.conf).
const E2E_MOCK_MODELS_BASE = process.env.AGORA_E2E_MOCK_MODELS_BASE ?? 'http://mock-models'
const ONLINE_CONN = {
  connectionId: 'openai_compatible',
  displayName: 'E2E Mock (online)',
  providerKind: 'openai_compatible',
  baseUrl: E2E_MOCK_MODELS_BASE,
} as const
const OFFLINE_CONN = {
  connectionId: 'openai',
  displayName: 'E2E Mock (offline)',
  providerKind: 'openai',
  // Bleibt ein nicht-aufloesbarer DNS-Name, damit der Discovery-Probe
  // der openai-Connection garantiert 0 Modelle zurueckgibt. mock-models
  // selbst liefert /, aber nicht /v1/models mit OpenAI-Schema — daher
  // nicht wiederverwenden.
  baseUrl: 'http://mock-models-unreachable:8080',
} as const

const E2E_MOCK_API_KEY = 'e2e-mock-placeholder'
const E2E_TOKEN = process.env.AGORA_AUTH_TOKEN ?? 'e2e-test-token-fixed-for-ci'
const E2E_PROXY_BASE = `http://127.0.0.1:${process.env.AGORA_PROXY_PORT ?? '80'}`

interface SeedConnection {
  connectionId: string
  displayName: string
  providerKind: string
  baseUrl: string
}

async function putConnection(conn: SeedConnection): Promise<void> {
  const url = `${E2E_PROXY_BASE}/api/llm/provider-connections/${conn.connectionId}`
  const body = {
    display_name: conn.displayName,
    provider_kind: conn.providerKind,
    base_url: conn.baseUrl,
    enabled: true,
    api_key: E2E_MOCK_API_KEY,
  }
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-Agora-Token': E2E_TOKEN,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`[e2e-globalSetup] seed ${conn.connectionId} failed: ${res.status} ${await res.text()}`)
  }
}

// Backend ist nach /healthz ready, aber der erste Seed kann selten einen
// Race mit dem Flask-Worker-Startup verlieren. 3 Versuche mit kleinem Backoff.
async function seedConnections(): Promise<void> {
  let lastErr: unknown
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await putConnection(ONLINE_CONN)
      await putConnection(OFFLINE_CONN)
      console.log('[e2e-globalSetup] seeded provider-connections (openai_compatible online, openai offline)')
      return
    } catch (err) {
      lastErr = err
      console.warn(`[e2e-globalSetup] seed attempt ${attempt} failed:`, err instanceof Error ? err.message : err)
      await new Promise((r) => setTimeout(r, 500))
    }
  }
  throw new Error(`[e2e-globalSetup] seeding provider-connections failed after 3 attempts: ${lastErr}`)
}

export default async function globalSetup() {
  if (process.env.AGORA_E2E_SKIP_STACK === 'true') {
    console.log('[e2e-globalSetup] AGORA_E2E_SKIP_STACK=true — assuming stack is already up');
  } else {
    const repoRoot = repoRootPath();
    const script = resolve(repoRoot, 'scripts', 'e2e-up.sh');
    console.log(`[e2e-globalSetup] running ${script}`);
    execSync(`bash "${script}"`, { stdio: 'inherit', cwd: repoRoot });
  }
  // Seeding muss in beiden Pfaden laufen — auch wenn der Stack von außen
  // hochgefahren wurde (AGORA_E2E_SKIP_STACK=true), brauchen die Specs
  // die beiden Provider-Connections.
  await seedConnections();
}