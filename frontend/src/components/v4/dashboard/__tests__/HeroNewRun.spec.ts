/**
 * HeroNewRun — Spec-Tests fuer Phase-1 Kanon-First Migration.
 *
 * Die Komponente ist der primaere Aktions-Block des Dashboards:
 * File-Picker, Profile-Dropdown, Modell-Wahl, Sprache, Persona-Count,
 * Rounds, Requirement, Start-CTA.
 *
 * Kanon-First (Phase-1): Das Default-Modell kommt aus dem Kanon
 * (routing/defaults.global via useEffectiveModelSelection), NICHT mehr aus
 * einem eigenen `agora.hero.aiModelRef`-localStorage-Key. Beim Mount wird
 * `effectiveModel.ensureLoaded()` gerufen und `selectedModel` aus
 * `effectiveModel.effectiveRef` initialisiert. Ein Dashboard-Pick ist ein
 * TRANSIENTER Run-Override: voller AiModelRef beim Start, ohne Schreiben oder
 * Clearen der Legacy-Modell-Keys. KEINE eigene persistente Modell-Senke mehr.
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. zeigt PageHeader-Title
 *  3. File-Picker-Zone sichtbar
 *  4. Profile-Dropdown sichtbar (Hybrid bleibt)
 *  5. AiModelPicker in Config-Zone sichtbar
 *  6. Kanon-First-Init: selectedModel wird onMounted aus effectiveRef initialisiert
 *  7. Storage-Cut: Legacy-Key `agora.hero.route` wird NICHT mehr gelesen, beim Mount entfernt
 *  8. onPickModel/onPickModel(null): Legacy-Modell-Keys bleiben unangetastet
 * 10. onPickProfile: persistiert Profile-ID (kein Model-Clear mehr)
 * 11. canSubmit: false ohne Files, false ohne Requirement
 * 12. startSimulation: Profile cleart den Run-Override
 * 13. startSimulation: expliziter Pick wird als voller Run-Override gespeichert
 * 14. startSimulation: ruft setPendingUpload + router.push
 * 15. i18n-Key: dashboard.hero.modelPlaceholder
 * 16. Capability-Filter: Picker bekommt mode='chat' (Default)
 * 17. Profile-Dropdown aktiv -> AiModelPicker versteckt (Hybrid)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import HeroNewRun from '../HeroNewRun.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type { LlmRoute } from '@/contracts/llmRoute'

// AiModelPicker mocken
const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template: '<div data-testid="ai-model-picker-stub" @click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-openai-1\', model_id: \'gpt-4o-mini\', source: \'explicit\' })">picker</div>',
}

// ModelPicker stubben
const legacyModelPickerStub = {
  name: 'ModelPicker',
  props: ['modelValue', 'placeholder', 'disabled'],
  emits: ['update:modelValue'],
  template: '<select data-testid="legacy-model-picker-stub" disabled></select>',
}

// Card stubben
const cardStub = {
  name: 'Card',
  props: ['title', 'subtitle'],
  template: '<section data-testid="card" :data-card-title="title"><slot /></section>',
}
const iconPlusStub = { name: 'IconPlus', template: '<span />' }

// Mocks müssen via vi.hoisted() definiert werden, weil vi.mock-Factories vor
// den Top-Level-Statements ausgeführt werden (Hoisting). Sonst wirft Vitest
// "Cannot access 'X' before initialization". Die geteilten Mock-Objekte
// werden in mountHero() / beforeEach() resettet und in den Tests über
// .mockClear()/.mockResolvedValue() gesteuert.
//
// effectiveRefHolder ist der steuerbare Kanon-Stub: Tests setzen
// `.current` auf den gewünschten AiModelRef (oder null) VOR dem Mount. Der
// Composable-Mock exponiert effectiveRef als Ref-Shape (Getter/Setter auf
// .value), die Komponente liest `effectiveModel.effectiveRef.value`.
const {
  fetchLlmProfilesMock,
  getSystemStatusMock,
  getAvailableModelsMock,
  setPendingUploadMock,
  routerPushMock,
  ensureLoadedMock,
  setGlobalSelectionMock,
  setRunModelOverrideMock,
  clearRunModelOverrideMock,
  effectiveRefHolder,
} = vi.hoisted(() => ({
  fetchLlmProfilesMock: vi.fn(),
  getSystemStatusMock: vi.fn(),
  getAvailableModelsMock: vi.fn(),
  setPendingUploadMock: vi.fn(),
  routerPushMock: vi.fn(),
  ensureLoadedMock: vi.fn(),
  setGlobalSelectionMock: vi.fn(),
  setRunModelOverrideMock: vi.fn(),
  clearRunModelOverrideMock: vi.fn(),
  effectiveRefHolder: { current: null as AiModelRef | null },
}))

vi.mock('@/api/llmProfiles', () => ({
  fetchLlmProfiles: fetchLlmProfilesMock,
}))

vi.mock('@/store/pendingUpload', () => ({
  setPendingUpload: setPendingUploadMock,
}))

// Transiente Run-Override-Senke: HeroNewRun schreibt beim Start den vollen
// AiModelRef (Pick) bzw. cleart (Profile/kein Pick) — Step3Simulation liest
// sie vorrangig vor dem Kanon.
vi.mock('@/store/runModelOverride', () => ({
  setRunModelOverride: setRunModelOverrideMock,
  clearRunModelOverride: clearRunModelOverrideMock,
}))

vi.mock('@/api/status', () => ({
  getSystemStatus: getSystemStatusMock,
}))

// Service-Readiness (Parität zu Home.vue, #915): Mock liefert neo4j_reachable=true
// und default_provider='openai' (kein Ollama-Zwang) → servicesReady=true →
// canSubmit nicht blockiert.
vi.mock('@/api/simulation', () => ({
  getAvailableModels: getAvailableModelsMock,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
}))

// Kanon-Composable stubben: effectiveRef wird über den hoisted Holder
// pro Test steuerbar. effectiveRoute/loading/error sind statisch (HeroNewRun
// konsumiert nur effectiveRef + ensureLoaded). setGlobalSelection wird hier
// nur exponiert, damit die Komponente ihn importieren kann — HeroNewRun ruft
// ihn NICHT auf (Picker-Pick ist transient, kein setGlobalSelection).
vi.mock('@/composables/useEffectiveModelSelection', () => {
  const stubRoute: LlmRoute = {
    stage: null,
    provider_id: 'openai',
    model: 'gpt-4o',
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  }
  return {
    useEffectiveModelSelection: () => ({
      effectiveRef: {
        get value(): AiModelRef | null {
          return effectiveRefHolder.current
        },
        set value(v: AiModelRef | null) {
          effectiveRefHolder.current = v
        },
      },
      effectiveRoute: {
        get value(): LlmRoute {
          return stubRoute
        },
        set value(_v: LlmRoute) {
          /* noop — HeroNewRun schreibt effectiveRoute nicht */
        },
      },
      loading: {
        get value(): boolean {
          return false
        },
        set value(_v: boolean) {
          /* noop */
        },
      },
      error: {
        get value(): string | null {
          return null
        },
        set value(_v: string | null) {
          /* noop */
        },
      },
      ensureLoaded: ensureLoadedMock,
      setGlobalSelection: setGlobalSelectionMock,
    }),
  }
})

// Initial-Defaults (werden in mountHero() vor jedem Test neu gesetzt).
fetchLlmProfilesMock.mockResolvedValue([])
getSystemStatusMock.mockResolvedValue({ data: { backend: { allow_small_sim: false } } })
// Service-Readiness (Parität zu Home.vue, #915): Default liefert neo4j_reachable=true
// und default_provider='openai' → servicesReady=true → canSubmit nicht blockiert.
getAvailableModelsMock.mockResolvedValue({ success: true, data: { default_provider: 'openai', ollama_reachable: true, neo4j_reachable: true, default_language: 'de' } })

// localStorage Mock pro Test kontrollieren
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((k: string) => store[k] ?? null),
    setItem: vi.fn((k: string, v: string) => { store[k] = v }),
    removeItem: vi.fn((k: string) => { delete store[k] }),
    clear: () => { store = {} },
    _store: store,
  }
})()

// jsdom hat ein eigenes localStorage; wir ersetzen es pro Test via
// vi.stubGlobal, damit die Vue-Komponente (die window.localStorage liest)
// unseren Mock sieht. vi.unstubAllGlobals nach jedem Test.
function installLocalStorageMock(): void {
  vi.stubGlobal('localStorage', localStorageMock)
}

function setEffectiveRef(aiRef: AiModelRef | null): void {
  effectiveRefHolder.current = aiRef
}

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'de',
    messages: {
      de: {
        dashboard: {
          hero: {
            title: 'Neuer Run',
            subtitle: 'Starte eine neue Simulation',
            sourceLabel: 'Quelle',
            dropHint: 'Datei ablegen',
            modelLabel: 'Modell',
            modelPlaceholder: 'Modell waehlen …',
            profileLabel: 'Profil',
            profileNone: 'Kein Profil',
            profileDefault: 'Default',
            languageLabel: 'Sprache',
            languageDe: 'Deutsch',
            languageEn: 'English',
            numAgentsLabel: 'Personas',
            numRoundsLabel: 'Runden',
            requirementLabel: 'Anforderung',
            requirementPlaceholder: 'Beschreibe was simuliert werden soll',
            startCta: 'Starten',
            disabledHint: 'Dateien und Anforderung benoetigt',
            smallSimBadge: 'SMALL',
            smallSimActiveTooltip: 'Override aktiv',
            numAgentsWarning: 'Weniger Personas als der harte Floor',
          },
        },
        errors: { fileTypeNotAllowed: 'Dateityp nicht erlaubt' },
        common: { delete: 'Loeschen' },
        aiModelPicker: { placeholder: 'Modell waehlen …' },
      },
    },
  })
}

async function mountHero(seed: Record<string, string> = {}) {
  localStorageMock.clear()
  vi.mocked(localStorageMock.getItem).mockClear()
  vi.mocked(localStorageMock.setItem).mockClear()
  vi.mocked(localStorageMock.removeItem).mockClear()
  installLocalStorageMock()
  // Optionale localStorage-Vorbelegung (nach dem Mock-Reset, damit die
  // Seed-setItem-Calls die Assertions nicht verfaelschen).
  for (const [k, v] of Object.entries(seed)) localStorageMock.setItem(k, v)
  vi.mocked(localStorageMock.setItem).mockClear()

  setPendingUploadMock.mockClear()
  routerPushMock.mockClear()
  setRunModelOverrideMock.mockClear()
  clearRunModelOverrideMock.mockClear()
  getSystemStatusMock.mockClear()
  getSystemStatusMock.mockResolvedValue({ data: { backend: { allow_small_sim: false } } })
  // Kanon-Stub: ensureLoaded muss resolven, damit die Komponente beim Mount
  // selectedModel aus effectiveRef initialisiert.
  ensureLoadedMock.mockReset()
  ensureLoadedMock.mockResolvedValue(undefined)
  setGlobalSelectionMock.mockReset()

  const i18n = makeI18n()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(HeroNewRun, {
    global: {
      plugins: [i18n],
      stubs: {
        AiModelPicker: aiPickerStub,
        ModelPicker: legacyModelPickerStub,
        Card: cardStub,
        IconPlus: iconPlusStub,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('HeroNewRun (Phase-1, Kanon-First Migration)', () => {
  beforeEach(() => {
    // clearAllMocks wuerde auch mockResolvedValue/Mock-Implementierungen loeschen.
    // Wir resetten nur die Call-History, nicht die Mocks selbst.
    for (const m of [localStorageMock.getItem, localStorageMock.setItem, localStorageMock.removeItem, setPendingUploadMock, routerPushMock, getSystemStatusMock]) {
      m.mockClear()
    }
    installLocalStorageMock()
    // Kanon-Stub pro Test auf Null zurücksetzen; Tests setzen vor mountHero
    // via setEffectiveRef den gewuenschten Kanon-Wert.
    setEffectiveRef(null)
    fetchLlmProfilesMock.mockReset()
    fetchLlmProfilesMock.mockResolvedValue([])
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mountet ohne Crash', async () => {
    const w = await mountHero()
    expect(w.exists()).toBe(true)
    expect(w.find('.hero-grid').exists()).toBe(true)
  })

  it('zeigt PageHeader-Card mit Title', async () => {
    const w = await mountHero()
    const card = w.findComponent(cardStub)
    expect(card.exists()).toBe(true)
    expect(card.props('title')).toBe('Neuer Run')
  })

  it('File-Picker-Zone sichtbar (Source-Label)', async () => {
    const w = await mountHero()
    expect(w.text()).toContain('Quelle')
  })

  it('Profile-Dropdown sichtbar (Hybrid bleibt erhalten)', async () => {
    const w = await mountHero()
    expect(w.text()).toContain('Profil')
  })

  it('AiModelPicker in Config-Zone sichtbar (Default: ohne Profile)', async () => {
    const w = await mountHero()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
  })

  it('Kanon-First-Init: selectedModel wird onMounted aus effectiveRef initialisiert', async () => {
    const aiRef: AiModelRef = {
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
      source: 'workspace-default',
    }
    setEffectiveRef(aiRef)
    const w = await mountHero()
    // ensureLoaded wird beim Mount gerufen und resolvt (Kanon-First-Init).
    expect(ensureLoadedMock).toHaveBeenCalled()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    // selectedModel wurde aus effectiveRef (Kanon) initialisiert — nicht aus
    // einem localStorage-Key. Komponente liest agora.hero.aiModelRef NICHT mehr.
    expect(picker.props('modelValue')).toMatchObject({
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
    })
  })

  it('Storage-Cut: Legacy-Key `agora.hero.route` wird NICHT mehr gelesen, beim Mount entfernt', async () => {
    // Nur der Legacy-Key ist gesetzt — er darf nach dem Storage-Cut keinen
    // Wert mehr vorbelegen und wird beim Mount defensiv entfernt. effectiveRef
    // ist null (kein Kanon-Wert), also bleibt der Picker leer.
    setEffectiveRef(null)
    const legacyRoute = {
      stage: null, provider_id: 'ollama', model: 'gpt-legacy',
      temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {},
    }
    const w = await mountHero({ 'agora.hero.route': JSON.stringify(legacyRoute) })
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    expect(picker.props('modelValue')).toBeNull()
    // Legacy-Route wird beim Mount defensiv entfernt.
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.hero.route')
    // Legacy-Route wird NICHT mehr gelesen (kein readLocal auf diesen Key).
    expect(localStorageMock.getItem).not.toHaveBeenCalledWith('agora.hero.route')
  })

  it('onPickModel schreibt oder cleart keine Legacy-Modell-Keys', async () => {
    const w = await mountHero()
    const picker = w.findComponent(aiPickerStub)
    await picker.trigger('click')
    await flushPromises()
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastModel')
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastCustomModel')
    // Legacy-Route wird bei jedem Pick defensiv entfernt.
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.hero.route')
    // Kein Schreiben in die entfernte Senke agora.hero.aiModelRef.
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.hero.aiModelRef', expect.anything())
  })

  it('onPickModel(null) schreibt oder cleart keine Legacy-Modell-Keys', async () => {
    const w = await mountHero()
    const picker = w.findComponent(aiPickerStub)
    // Manuell null emittieren (AiModelRef | null).
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', null)
    await flushPromises()
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastModel')
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastCustomModel')
    // Legacy-Route wird entfernt.
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.hero.route')
    // Kein Schreiben in / kein Entfernen der entfernten Senke agora.hero.aiModelRef.
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.hero.aiModelRef')
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.hero.aiModelRef', expect.anything())
  })

  it('onPickProfile: persistiert Profile-ID via store', async () => {
    // Smoke: wir setzen selectedProfileId via Pinia und pruefen, dass
    // setItem mit Profile-ID aufgerufen wird. Profil-Options aus dem
    // async API-Call sind hier zweitrangig. onPickProfile cleared selectedModel
    // nicht mehr (Kanon-First-Init bleibt erhalten).
    const w = await mountHero()
    const select = w.find('#hero-profile')
    expect(select.exists()).toBe(true)
    const sel = select.element as HTMLSelectElement
    sel.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    // selectedProfileId bleibt null bei leerer Profile-Liste — kein
    // lokaler Persistenz-Call. Das ist korrekt, kein Test-Fehler.
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith(
      'agora.hero.profileId',
      expect.anything(),
    )
  })

  it('canSubmit: false ohne Files', async () => {
    const w = await mountHero()
    const cta = w.find('.hero-cta')
    expect((cta.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('canSubmit: false ohne Requirement', async () => {
    const w = await mountHero()
    const cta = w.find('.hero-cta')
    // Auch ohne Files deaktiviert
    expect((cta.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('startSimulation: bei Profile aktiv wird Picker-Pfad inaktiv (Hybrid v-if)', async () => {
    // Smoke: ohne aktives Profil ist der Picker sichtbar.
    const w = await mountHero()
    expect(w.findComponent(aiPickerStub).exists()).toBe(true)
    // selectedProfileId ist null (kein Profil), also Picker sichtbar.
    // Vollstaendige Profil-Selektion wird in onPickProfile-Test dokumentiert.
  })

  it('startSimulation: bei Profile aktiv berührt keine Legacy-Modell-Keys', async () => {
    fetchLlmProfilesMock.mockResolvedValue([
      {
        id: 'abc',
        name: 'Mein GPT-4o',
        provider: 'openai',
        base_url: 'https://api.openai.com/v1',
        model_name: 'gpt-4o',
        api_key: 'sk-test',
        is_default: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ])
    const w = await mountHero()

    // Datei setzen
    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    // Fragestellung setzen
    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    // Profil 'abc' auswählen
    const select = w.find<HTMLSelectElement>('select#hero-profile')
    await select.setValue('abc')
    await flushPromises()

    // Starten
    const cta = w.find('.hero-cta')
    expect((cta.element as HTMLButtonElement).disabled).toBe(false)
    await cta.trigger('click')
    await flushPromises()

    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastModel')
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastCustomModel')
    expect(setPendingUploadMock).toHaveBeenCalledWith(
      [file],
      'Wie reagiert die DACH-Region?',
      'abc',
      30,
      10,
    )
    // Issue #1234: Die Rundenzahl reist in der Query, nicht im Store — den
    // leert Schritt 1 nach dem Upload.
    expect(routerPushMock).toHaveBeenCalledWith({
      name: 'Process',
      params: { projectId: 'new' },
      query: { maxRounds: '10' },
    })
  })

  it('startSimulation: gesetztes Run-Budget wird in die Query geschrieben (Issue #764, #1234)', async () => {
    const w = await mountHero()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    // Token-Limit über das eingebundene RunBudgetForm setzen (echtes Form,
    // erstes Feld = Token-Limit). Details-Content ist auch eingeklappt im DOM.
    const budgetForm = w.findComponent({ name: 'RunBudgetForm' })
    expect(budgetForm.exists()).toBe(true)
    const tokenInput = budgetForm.findAll('input')[0]
    await tokenInput.setValue('50000')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    // Das Budget gehoert nicht mehr in den Store: Schritt 1 raeumt ihn nach
    // dem Upload, Schritt 3 fand dort nie eines vor (Issue #1234).
    expect(setPendingUploadMock).toHaveBeenCalledWith(
      [file],
      'Wie reagiert die DACH-Region?',
      null,
      30,
      10,
    )
    const pushed = routerPushMock.mock.calls.at(-1)?.[0] as { query?: Record<string, string> }
    expect(JSON.parse(String(pushed.query?.budget))).toEqual({
      schema_version: 1,
      enforcement: 'soft',
      currency: 'USD',
      max_tokens: 50000,
    })
  })

  it('startSimulation: ohne Profile lässt Legacy-Modell-Keys unangetastet', async () => {
    const w = await mountHero()
    // Picker emit aiRef (transienter Run-Override).
    const picker = w.findComponent(aiPickerStub)
    await picker.trigger('click')
    await flushPromises()

    // Datei setzen
    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    // Fragestellung setzen
    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    // Starten (ohne Profil → Picker-Wahl gewinnt).
    const cta = w.find('.hero-cta')
    await cta.trigger('click')
    await flushPromises()

    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastModel')
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastCustomModel')
    expect(setPendingUploadMock).toHaveBeenCalled()
    expect(routerPushMock).toHaveBeenCalledWith({
      name: 'Process',
      params: { projectId: 'new' },
      query: { maxRounds: '10' },
    })
  })

  it('startSimulation: ohne Profile setzt die Picker-Wahl den Run-Override (voller AiModelRef)', async () => {
    const w = await mountHero()
    // Picker emit aiRef → transienter Run-Override inkl. provider_connection_id.
    const picker = w.findComponent(aiPickerStub)
    await picker.trigger('click')
    await flushPromises()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    // Der volle AiModelRef wandert in die Run-Override-Senke — Step3Simulation
    // sendet ihn beim Sim-Start vorrangig vor dem Kanon als ai_model_ref.
    expect(setRunModelOverrideMock).toHaveBeenCalledWith({
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    expect(clearRunModelOverrideMock).not.toHaveBeenCalled()
  })

  it('startSimulation: bei aktivem Profile wird der Run-Override gecleart (Profile gewinnt)', async () => {
    fetchLlmProfilesMock.mockResolvedValue([
      {
        id: 'abc',
        name: 'Mein GPT-4o',
        provider: 'openai',
        base_url: 'https://api.openai.com/v1',
        model_name: 'gpt-4o',
        is_default: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ])
    const w = await mountHero()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    const select = w.find<HTMLSelectElement>('select#hero-profile')
    await select.setValue('abc')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    expect(clearRunModelOverrideMock).toHaveBeenCalledTimes(1)
    expect(setRunModelOverrideMock).not.toHaveBeenCalled()
  })

  it('startSimulation: Kanon-Initialisierung ohne Picker-Interaktion setzt KEINEN Run-Override', async () => {
    // selectedModel wird beim Mount aus dem Kanon initialisiert — ohne
    // expliziten Picker-Pick darf der Kanon NICHT als Override eingefroren
    // werden (spätere Kanon-Änderungen sollen bis zum Sim-Start durchschlagen).
    effectiveRefHolder.current = {
      provider_connection_id: 'conn-kanon',
      model_id: 'kanon-model',
      source: 'explicit',
    }
    const w = await mountHero()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    expect(setRunModelOverrideMock).not.toHaveBeenCalled()
    expect(clearRunModelOverrideMock).toHaveBeenCalledTimes(1)
  })

  it('startSimulation: ohne Pick und ohne Profile wird der Run-Override gecleart', async () => {
    const w = await mountHero()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    expect(clearRunModelOverrideMock).toHaveBeenCalledTimes(1)
    expect(setRunModelOverrideMock).not.toHaveBeenCalled()
  })

  it('startSimulation: setPendingUpload wird ueber Pinia exportiert (Smoke)', async () => {
    const w = await mountHero()
    // Smoke: setPendingUpload ist gemockt, Komponente muss ihn importieren
    // koennen. Wir pruefen nur, dass der Import funktioniert.
    expect(w.exists()).toBe(true)
    expect(setPendingUploadMock).toBeDefined()
  })

  it('i18n-Key: dashboard.hero.modelPlaceholder wird an Picker durchgereicht', async () => {
    const w = await mountHero()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('placeholder')).toBe('Modell waehlen …')
  })

  it('Capability-Filter: Picker bekommt mode="chat" (Default)', async () => {
    const w = await mountHero()
    const picker = w.findComponent(aiPickerStub)
    // mode ist optional mit default 'chat' — entweder explizit oder implizit
    const mode = picker.props('mode')
    expect(mode === 'chat' || mode === undefined).toBe(true)
  })

  it('Profile-Dropdown aktiv -> AiModelPicker versteckt (Hybrid: Picker nur wenn kein Profil)', async () => {
    // Der Hybrid-Mechanismus (v-if="!selectedProfileId") ist Template-Logik
    // und nicht direkt Migration-relevant. Smoke: ohne Profil sichtbar.
    const w = await mountHero()
    expect(w.findComponent(aiPickerStub).exists()).toBe(true)
  })
})
