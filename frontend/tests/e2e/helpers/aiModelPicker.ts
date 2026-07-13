import type { BrowserContext, Locator, Page } from '@playwright/test'
import { expect } from '@playwright/test'
import { AiModelPickerTestId } from './testIds'
import { injectAuthToken } from './auth'

/**
 * AiModelPicker — Playwright-Helper fuer E2E.
 *
 * Stellt Locator- und Action-Funktionen bereit, die ausschliesslich
 * auf den data-testid-Attributen aus `./testIds.ts` aufsetzen. Klass-
 * oder ARIA-Selektoren werden bewusst NICHT verwendet, damit
 * CSS-Refactors oder i18n-Aenderungen die Specs nicht brechen.
 *
 * Slice 5.6-Prep: Skeleton. Die hier exponierten Funktionen werden
 * in 5.6 final von der Spec aktiv genutzt (Skip-Annotationen raus,
 * sobald 5.4 die Komponente in den Ziel-Views mountet).
 *
 * Voraussetzungen (von 5.4 zu erfuellen, dokumentiert in slice-5-subplan.md):
 *   - AiModelPicker in mindestens einer v4-View gemountet
 *     (Empfehlung slice-5: SettingsGeneralView, HeroNewRun,
 *     StepModelOverrideChip).
 *   - ProviderConnection-Backend liefert mind. eine 'available'-Connection
 *     und eine 'unavailable'-Connection (siehe Test 2).
 *   - Run-Snapshot-Endpoint /api/runs/<run_id>/llm-routing liefert das
 *     canonical `ai_route`-Feld (siehe PR #700, ai_provider_contract.AiRoute).
 */

/**
 * Login-Shim.
 *
 * Agora laeuft im Single-User-Token-Mode (siehe health.spec.ts Test 4).
 * Es gibt kein klassisches Login-Formular — der Token wird per
 * `injectAuthToken()` aus `helpers/auth.ts` in localStorage injiziert
 * und vom Frontend als Bearer-Token mitgesendet.
 *
 * Akzeptiert wahlweise Page (zieht context raus) oder direkt den
 * BrowserContext, damit Specs bequem `await login(page)` schreiben
 * koennen.
 */
export async function login(
  target: Page | BrowserContext,
  token?: string,
): Promise<void> {
  const context: BrowserContext = 'context' in target ? target.context() : target
  await injectAuthToken(context, token)
}

/**
 * Locator fuer den AiModelPicker-Root-Container.
 * Mehrere Picker pro Seite sind erlaubt; ueber `index` oder
 * `.filter()` kann ein bestimmter Picker gewaehlt werden.
 */
export function getPicker(page: Page): Locator {
  return page.getByTestId(AiModelPickerTestId.root)
}

/**
 * Locator fuer den Trigger-Input (zeigt aktuell gewaehltes Modell
 * oder Platzhalter). Fokus auf dieses Element oeffnet den Combobox.
 */
export function getPickerInput(page: Page, picker?: Locator): Locator {
  const scope = picker ?? getPicker(page)
  return scope.getByTestId(AiModelPickerTestId.input)
}

/**
 * Locator fuer das Suchfeld (sichtbar, sobald der Picker geoeffnet ist).
 */
export function getPickerSearch(page: Page, picker?: Locator): Locator {
  const scope = picker ?? getPicker(page)
  return scope.getByTestId(AiModelPickerTestId.search)
}

/**
 * Locator fuer eine bestimmte Provider-Group (z. B. fuer
 * Sichtbarkeits-Assertion "Ollama-Gruppe vorhanden").
 */
export function getGroupByConnectionId(
  page: Page,
  providerConnectionId: string,
  picker?: Locator,
): Locator {
  const scope = picker ?? getPicker(page)
  return scope.locator(
    `[data-testid="${AiModelPickerTestId.group}"][data-provider-connection-id="${cssEscape(providerConnectionId)}"]`,
  )
}

/**
 * Locator fuer eine bestimmte Modell-Option.
 *
 * Selektiert (provider_connection_id, model_id) — beide Attribute
 * sind Pflicht, damit die Assertion nicht versehentlich auf das
 * falsche Modell in einer anderen Provider-Gruppe passt.
 */
export function getOption(
  page: Page,
  args: { providerConnectionId: string; modelId: string },
  picker?: Locator,
): Locator {
  const scope = picker ?? getPicker(page)
  return scope.locator(
    `[data-testid="${AiModelPickerTestId.option}"][data-provider-connection-id="${cssEscape(args.providerConnectionId)}"][data-model-id="${cssEscape(args.modelId)}"]`,
  )
}

/**
 * Action: Picker oeffnen (Fokus auf Trigger-Input).
 *
 * Wartet NICHT explizit auf das Oeffnen des Combobox-Contents, weil
 * reka-ui das Content-Portal in einer separaten Subtree rendert.
 * Specs sollten direkt mit `expect(...).toBeVisible()` auf der
 * gewuenschten Option arbeiten — Playwright wartet dann implizit.
 */
export async function openPicker(page: Page, picker?: Locator): Promise<void> {
  await getPickerInput(page, picker).click()
}

/**
 * Action: Modell per Klick auswaehlen.
 *
 * Voraussetzung: Picker ist bereits geoeffnet (openPicker()).
 * Erwartet: die Option ist sichtbar UND nicht disabled.
 */
export async function selectOptionByClick(
  page: Page,
  args: { providerConnectionId: string; modelId: string },
  picker?: Locator,
): Promise<void> {
  const option = getOption(page, args, picker)
  await expect(option).toBeVisible()
  await expect(option).toBeEnabled()
  await option.click()
}

/**
 * Action: Tastatur-Drill ↓↓↑Enter.
 *
 * Erwartet: Picker ist geoeffnet, der erste navigierbare Eintrag
 * wird mit ArrowDown markiert. Specs muessen pruefen, dass das
 * markierte Item bei jedem Schritt wechselt.
 */
export async function drillKeyboard(
  page: Page,
  picker?: Locator,
): Promise<void> {
  const input = getPickerInput(page, picker)
  // Erstes ArrowDown oeffnet ggf. das Drop-Down falls der Picker
  // nicht durch Klick geoeffnet wurde; danach folgen zwei ↓, ein
  // ↑ und Enter. reka-ui Combobox-Logik ueber List-Navigation.
  await input.press('ArrowDown')
  await input.press('ArrowDown')
  await input.press('ArrowUp')
  await input.press('Enter')
}

/**
 * Action: aktuelle Selektion aus dem Trigger-Input lesen.
 *
 * Liefert den sichtbaren Text (Display-Value) des Trigger-Inputs.
 * Specs koennen darauf asserten, dass die Auswahl angezeigt wird.
 */
export async function readSelectedLabel(
  page: Page,
  picker?: Locator,
): Promise<string> {
  return (await getPickerInput(page, picker).inputValue()).trim()
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/**
 * CSS.escape-Polyfill, weil nicht alle Playwright-Versionen einen
 * eingebauten Escape fuer Attribut-Selektoren liefern. Strings mit
 * Sonderzeichen (z. B. Doppelpunkt in "qwen2.5:14b") wuerden
 * sonst den Selektor zerlegen.
 */
function cssEscape(value: string): string {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(value)
  }
  // Minimaler Fallback: nur Zeichen escapen, die in
  // CSS-Attribut-Selektoren problematisch sind.
  return value.replace(/(["\\\]\[])/g, '\\$1')
}
