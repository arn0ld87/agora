import type { BrowserContext } from '@playwright/test';

// Verifiziert gegen frontend/src/api/index.ts:
// window.localStorage.getItem('agora_token') ist der primäre Auth-Storage-Pfad
// (Zeile 41 in api/index.ts). Dieser Key muss mit dem Frontend-Code synchron bleiben.
const STORAGE_KEY = 'agora_token';

export async function injectAuthToken(context: BrowserContext, token?: string): Promise<void> {
  const value = token ?? process.env.AGORA_AUTH_TOKEN ?? 'e2e-test-token-fixed-for-ci';
  // Token vor jeder Navigation injizieren, damit der erste Request den Bearer-Header
  // mitschickt. addInitScript wird vor dem Page-Load ausgeführt.
  await context.addInitScript(([k, v]: [string, string]) => {
    window.localStorage.setItem(k, v);
  }, [STORAGE_KEY, value] as [string, string]);
}

export function bearerHeader(token?: string): Record<string, string> {
  const value = token ?? process.env.AGORA_AUTH_TOKEN ?? 'e2e-test-token-fixed-for-ci';
  return { Authorization: `Bearer ${value}` };
}
