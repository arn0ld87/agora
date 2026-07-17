/**
 * OnboardingView — Vitest-Smokes (Onboarding Slice 2).
 *
 * Tests:
 *  1. Mountet ohne Crash.
 *  2. Resume: startet bei `state.current_step` statt immer bei 'welcome'.
 *  3. i18n-Keys lösen auf (kein "onboarding.*"-Rohdot im DOM).
 *  4. welcome-Schritt: Betriebsmodus wählen + Weiter → completeOnboardingStep('welcome', mode).
 *  5. "Später einrichten" ruft dismissOnboarding() und navigiert zum Dashboard.
 *  6. summary-Schritt: 409 "onboarding_incomplete" (top-level `missing` im
 *     Envelope, normalisiert nach `details.missing` in api/profile.ts) zeigt
 *     die tatsächlichen missing-Punkte an — nicht den Client-Fallback.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'
import { ApiError } from '@/api/envelope'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import type { OnboardingState, OnboardingStatusResponse, UserProfile } from '@/contracts/userProfileContract'
import type { ProviderConnection } from '@/contracts/aiProviderContract'

vi.mock('@/api/profile', () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
  deleteAvatar: vi.fn(),
  fetchAvatarBlob: vi.fn().mockResolvedValue(null),
  getOnboardingStatus: vi.fn(),
  completeOnboardingStep: vi.fn(),
  completeOnboarding: vi.fn(),
  dismissOnboarding: vi.fn(),
  reopenOnboarding: vi.fn(),
  avatarUrl: vi.fn(() => null),
}))

vi.mock('@/api/providerConnections', () => ({
  listProviderConnections: vi.fn(),
}))

vi.mock('@/components/v4/shell/AppShell.vue', () => ({
  default: {
    name: 'AppShell',
    props: ['breadcrumbs'],
    template: '<div class="app-shell-stub"><slot /></div>',
  },
}))
vi.mock('@/components/v4/shell/PageHeader.vue', () => ({
  default: {
    name: 'PageHeader',
    props: ['title', 'subtitle'],
    template: '<div class="page-header-stub"><h1>{{ title }}</h1></div>',
  },
}))

import {
  completeOnboarding,
  completeOnboardingStep,
  dismissOnboarding,
  getOnboardingStatus,
  getProfile,
} from '@/api/profile'
import { listProviderConnections } from '@/api/providerConnections'
import OnboardingView from '../OnboardingView.vue'

type MockFn = ReturnType<typeof vi.fn>
const _getProfile = getProfile as unknown as MockFn
const _getOnboardingStatus = getOnboardingStatus as unknown as MockFn
const _completeOnboardingStep = completeOnboardingStep as unknown as MockFn
const _completeOnboarding = completeOnboarding as unknown as MockFn
const _dismissOnboarding = dismissOnboarding as unknown as MockFn
const _listProviderConnections = vi.mocked(listProviderConnections)

function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    avatar_ref: null,
    display_name: 'Alex Schneider',
    username: null,
    role: null,
    organisation: null,
    language: 'de',
    timezone: 'Europe/Berlin',
    report_language: 'de',
    theme: 'system',
    privacy_mode: 'standard',
    created_at: '2026-07-11T00:00:00Z',
    updated_at: '2026-07-11T00:00:00Z',
    ...overrides,
  }
}

function makeOnboardingState(overrides: Partial<OnboardingState> = {}): OnboardingState {
  return {
    status: 'in_progress',
    operating_mode: null,
    current_step: 'welcome',
    completed_steps: [],
    created_at: '2026-07-11T00:00:00Z',
    updated_at: '2026-07-11T00:00:00Z',
    ...overrides,
  }
}

function makeOnboardingStatus(
  overrides: Partial<OnboardingStatusResponse> = {},
): OnboardingStatusResponse {
  return {
    state: makeOnboardingState(),
    requirements: {
      profile_valid: false,
      chat_model_configured: false,
      embedding_configured: false,
      embedding_source: 'none',
    },
    onboarding_required: true,
    ...overrides,
  }
}

function makeProviderConnection(overrides: Partial<ProviderConnection> = {}): ProviderConnection {
  return {
    id: 'test-connection-1',
    provider_kind: 'ollama',
    display_name: 'Test Ollama',
    transport: 'local',
    auth_mode: 'none',
    base_url: null,
    enabled: true,
    status: 'connected',
    status_message: null,
    secret_ref: null,
    capabilities: {},
    created_at: null,
    updated_at: null,
    last_tested_at: null,
    ...overrides,
  }
}

function makeI18n() {
  return createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
}

async function mountView(attachTo?: Element) {
  const router = makeTestRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  await router.push('/onboarding')
  await router.isReady()
  const wrapper = mount(OnboardingView, {
    attachTo,
    global: { plugins: [router, pinia, makeI18n()] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('OnboardingView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('Test 1: mountet ohne Crash', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())

    const { wrapper } = await mountView()
    expect(wrapper.exists()).toBe(true)
  })

  it('Test 2: Resume — startet bei state.current_step statt immer bei welcome', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'privacy',
          completed_steps: ['welcome', 'profile', 'providers', 'chat_model', 'embeddings'],
          operating_mode: 'local',
        }),
      }),
    )

    const { wrapper } = await mountView()
    expect(wrapper.text()).toContain(de.onboarding.privacy.title)
    expect(wrapper.text()).not.toContain(de.onboarding.welcome.title)
  })

  it('Test 3: i18n-Keys lösen auf (kein Rohdot im DOM)', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())

    const { wrapper } = await mountView()
    expect(wrapper.text()).not.toMatch(/onboarding\.[a-zA-Z]/)
  })

  it('Test 4: welcome-Schritt — Modus wählen + Weiter ruft completeOnboardingStep', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())
    _completeOnboardingStep.mockResolvedValue(
      makeOnboardingState({ current_step: 'profile', completed_steps: ['welcome'], operating_mode: 'hybrid' }),
    )

    const { wrapper } = await mountView()
    const modeButtons = wrapper.findAll('.onboarding-mode-card')
    expect(modeButtons.length).toBe(3)
    await modeButtons[1].trigger('click') // hybrid

    const nextBtn = wrapper.findAll('button').find((b) => b.text() === de.onboarding.wizard.nextBtn)
    expect(nextBtn).toBeTruthy()
    await nextBtn?.trigger('click')
    await flushPromises()

    expect(_completeOnboardingStep).toHaveBeenCalledWith('welcome', 'hybrid')
    expect(wrapper.text()).toContain(de.onboarding.profile.title)
  })

  it('Test 5: "Später einrichten" ruft dismissOnboarding und navigiert zum Dashboard', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())
    _dismissOnboarding.mockResolvedValue(makeOnboardingState({ status: 'dismissed' }))

    const { wrapper, router } = await mountView()
    const laterBtn = wrapper.findAll('button').find((b) => b.text() === de.onboarding.wizard.laterBtn)
    expect(laterBtn).toBeTruthy()
    await laterBtn?.trigger('click')
    await flushPromises()

    expect(_dismissOnboarding).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  it('Test 7: embeddings-Step rendert Legacy-Hinweis, wenn embedding_source=legacy', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'embeddings',
          completed_steps: ['welcome', 'profile', 'providers', 'chat_model'],
          operating_mode: 'local',
        }),
        requirements: {
          profile_valid: true,
          chat_model_configured: true,
          embedding_configured: true,
          embedding_source: 'legacy',
        },
      }),
    )

    const { wrapper } = await mountView()
    const hint = wrapper.find('.onboarding-step__legacy-hint')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain(de.onboarding.embeddings.legacyHint)
  })

  it('Test 8: embeddings-Step zeigt KEINEN Legacy-Hinweis, wenn embedding_source=store', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'embeddings',
          completed_steps: ['welcome', 'profile', 'providers', 'chat_model'],
          operating_mode: 'local',
        }),
        requirements: {
          profile_valid: true,
          chat_model_configured: true,
          embedding_configured: true,
          embedding_source: 'store',
        },
      }),
    )

    const { wrapper } = await mountView()
    expect(wrapper.find('.onboarding-step__legacy-hint').exists()).toBe(false)
  })

  it('Test 6: summary — 409 onboarding_incomplete zeigt server-seitige missing-Liste, nicht den Client-Fallback', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    // Requirements sind clientseitig ALLE erfüllt — der Client-Fallback wäre
    // also leer. Trotzdem meldet das Backend "chat_model_configured" fehlend
    // (Race/Server-Wahrheit gewinnt) — die UI muss GENAU diese Liste zeigen.
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'summary',
          completed_steps: ['welcome', 'profile', 'providers', 'chat_model', 'embeddings', 'privacy'],
          operating_mode: 'local',
        }),
        requirements: {
          profile_valid: true,
          chat_model_configured: true,
          embedding_configured: true,
          embedding_source: 'store',
        },
      }),
    )
    // Simuliert das bereits normalisierte api/profile.ts-Ergebnis: die
    // TOP-LEVEL `missing`-Liste aus dem 409-Envelope landet in details.missing
    // (siehe api/__tests__/profile.spec.ts für die Wire-Format-Normalisierung selbst).
    _completeOnboarding.mockRejectedValue(
      new ApiError({
        code: 'onboarding_incomplete',
        status: 409,
        message: 'onboarding incomplete',
        details: { missing: ['chat_model_configured'] },
      }),
    )

    const { wrapper, router } = await mountView()
    const finishBtn = wrapper.findAll('button').find((b) => b.text() === de.onboarding.wizard.finishBtn)
    expect(finishBtn).toBeTruthy()
    await finishBtn?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(de.onboarding.requirements.chatModelConfigured)
    expect(wrapper.text()).toContain(de.onboarding.summary.incompleteNotice)
    // Button bleibt aktiv (kein disabled-Attribut nach Fehler).
    expect(finishBtn?.attributes('disabled')).toBeUndefined()
    // Keine Navigation weg von /onboarding.
    expect(router.currentRoute.value.name).toBe('Onboarding')
  })

  it('Test 9: Fortschritt und Schrittinhalt besitzen eindeutige Landmarken und Status-Semantik', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())

    const { wrapper } = await mountView()
    expect(wrapper.get('.onboarding-steps').attributes('aria-label')).toBe(
      de.onboarding.wizard.progressLabel,
    )
    expect(wrapper.get('.onboarding-steps__item--current').attributes('aria-current')).toBe(
      'step',
    )
    wrapper.get('section[aria-labelledby="onboarding-step-title"]')
  })

  it('Test 10: fokussiert nach einem Schrittwechsel die neue Überschrift', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())
    _completeOnboardingStep.mockResolvedValue(
      makeOnboardingState({
        current_step: 'profile',
        completed_steps: ['welcome'],
        operating_mode: 'hybrid',
      }),
    )
    const host = document.createElement('div')
    document.body.append(host)
    const { wrapper } = await mountView(host)

    await wrapper.findAll('.onboarding-mode-card')[1].trigger('click')
    const nextBtn = wrapper.findAll('button').find((button) =>
      button.text().includes(de.onboarding.wizard.nextBtn),
    )
    await nextBtn?.trigger('click')
    await flushPromises()

    const heading = wrapper.get('#onboarding-step-title')
    expect(heading.text()).toBe(de.onboarding.profile.title)
    expect(document.activeElement).toBe(heading.element)
    wrapper.unmount()
    host.remove()
  })

  // Phase 2 Onboarding-Verfeinerung: Granularität + Skip-Button.
  //
  // Granularität: providers zeigt den Connection-Store-Status (nicht
  // chat_model_configured). chat_model und embeddings bleiben am
  // Backend-Requirements-Flag. providers und chat_model sind damit
  // nicht mehr redundant.
  it('Test 11: providers-Step zeigt pending, wenn keine Connections geladen — auch wenn chat_model_configured=true', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'providers',
          completed_steps: ['welcome'],
          operating_mode: 'local',
        }),
        requirements: {
          profile_valid: false,
          // Model ist bereits global gesetzt …
          chat_model_configured: true,
          embedding_configured: false,
          embedding_source: 'none',
        },
      }),
    )
    // … aber es existiert (noch) keine konfigurierte Provider-Connection.
    _listProviderConnections.mockResolvedValue({ items: [], total: 0 })

    const { wrapper } = await mountView()
    // providers.configured() wertet connections aus, nicht chat_model_configured.
    expect(wrapper.text()).toContain(de.onboarding.providers.notConfigured)
    expect(wrapper.text()).not.toContain(de.onboarding.providers.configured)
  })

  // Skip-Button: auf Statusschritten nur sichtbar, wenn der Step
  // tatsächlich configured ist. Sonst markiert ein voreilig geklickter
  // "Weiter"-Button den Step als completed, obwohl nichts eingerichtet ist.
  it('Test 12: providers-Step blendet Weiter-Button aus, solange providers.configured() === false', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'providers',
          completed_steps: ['welcome'],
          operating_mode: 'local',
        }),
      }),
    )
    _listProviderConnections.mockResolvedValue({ items: [], total: 0 })

    const { wrapper } = await mountView()
    const nextBtn = wrapper
      .findAll('button')
      .find((b) => b.text() === de.onboarding.wizard.nextBtn)
    expect(nextBtn).toBeFalsy()
  })

  it('Test 13: providers-Step zeigt Weiter-Button, sobald Connections geladen sind', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(
      makeOnboardingStatus({
        state: makeOnboardingState({
          current_step: 'providers',
          completed_steps: ['welcome'],
          operating_mode: 'local',
        }),
      }),
    )
    _listProviderConnections.mockResolvedValue({ items: [makeProviderConnection({ id: 'p1' })], total: 1 })

    const { wrapper } = await mountView()
    const nextBtn = wrapper
      .findAll('button')
      .find((b) => b.text() === de.onboarding.wizard.nextBtn)
    expect(nextBtn).toBeTruthy()
  })
})
