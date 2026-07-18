import type { Page } from '@playwright/test';
import { authHeader } from './auth';

/**
 * Slice 7.2 Follow-up (Issue #739 Sub-Slice 5/5) — Onboarding-Guard-Bypass
 * für Accessibility-Gates.
 *
 * `router/onboardingGuard.ts:32` redirected JEDE nicht-exempte Route auf
 * `/onboarding`, solange `onboarding_required=true` ist (Default-Zustand
 * eines frischen E2E-Stacks). Ohne diesen Aufruf testet axe-core faktisch
 * nur die Onboarding-Seite statt der zehn Zielrouten aus
 * golden-gate-accessibility.spec.ts.
 *
 * `POST /api/onboarding/dismiss` ist idempotent
 * (backend/app/services/onboarding_state_store.py::dismiss — no-op, falls
 * der Status bereits 'completed' ist) und darf daher gefahrlos in jedem
 * `beforeEach` erneut aufgerufen werden.
 */
export async function ensureOnboardingDismissed(page: Page): Promise<void> {
  const res = await page.request.post('/api/onboarding/dismiss', {
    headers: authHeader(),
  });
  if (!res.ok()) {
    throw new Error(
      `[ensureOnboardingDismissed] POST /api/onboarding/dismiss failed: ${res.status()} ${await res.text()}`,
    );
  }
}
