import type { BrowserContext, Locator, Page } from '@playwright/test'
import { expect } from '@playwright/test'
import { AiModelPickerTestId, LlmRoutingTestId } from './testIds'
import { injectAuthToken } from './auth'

/**
 * AiModelPicker — Playwright-Helper fuer E2E (Slice 5.6 final).
 *
 * Stellt Locator- und Action-Funktionen bereit, die ausschliesslich
 * auf den data-testid-Attributen aus `./testIds.ts` aufsetzen. Klass-
 * oder ARIA-Selektoren werden bewusst NICHT verwendet, damit
 * CSS-Refactors oder i18n-Aenderungen die Specs nicht brechen.
 *
 * WICHTIG — ComboboxPortal-Topologie:
 *   reka-ui `ComboboxPortal` teleportiert den Combobox-Content
 *   (Search, Empty, Groups, Options) in einen Portal am <body>. Diese
 *   Elemente liegen NICHT mehr innerhalb des Picker-Root-Scope. Daher
 *   sind getPickerSearch / getPickerEmpty / getGroupByConnectionId /
 *   getOption PAGE-LEVEL (kein Picker-Scope) implementiert.
 *   Nur der Trigger-Anchor (ComboboxInput + Trigger) bleibt im
 *   Picker-Root → getPickerInput ist weiterhin SCOPED auf den Picker.
 */

/**
 * Login-Shim. Agora laeuft im Single-User-Token-Mode — der Token wird
 * per `injectAuthToken()` in localStorage injiziert.
 */
export async function login(
  target: Page | BrowserContext,
  token?: string,
): Promise<void> {
  const context: BrowserContext = 'context' in target ? target.context() : target
  await injectAuthToken(context, token)
}

/** Locator fuer den AiModelPicker-Root-Container. */
export function getPicker(page: Page): Locator {
  return page.getByTestId(AiModelPickerTestId.root)
}

/**
 * Locator fuer den Trigger-Input (Anchor) — bleibt im Picker-Root,
 * NICHT portaled. Darum SCOPED auf den Picker.
 */
export function getPickerInput(page: Page, picker?: Locator): Locator {
  const scope = picker ?? getPicker(page)
  return scope.getByTestId(AiModelPickerTestId.input)
}

/**
 * PAGE-LEVEL — ComboboxPortal teleportiert die Suche nach <body>.
 * `picker` wird bewusst ignoriert (Signatur bleibt aus Kompatibilitaet).
 */
export function getPickerSearch(page: Page, _picker?: Locator): Locator {
  return page.getByTestId(AiModelPickerTestId.search)
}

/** PAGE-LEVEL — Empty-Hinweis lebt im portaled Content. */
export function getPickerEmpty(page: Page, _picker?: Locator): Locator {
  return page.getByTestId(AiModelPickerTestId.empty)
}

/** PAGE-LEVEL — Provider-Group lebt im portaled Content. */
export function getGroupByConnectionId(
  page: Page,
  providerConnectionId: string,
  _picker?: Locator,
): Locator {
  return page.locator(
    `[data-testid="${AiModelPickerTestId.group}"][data-provider-connection-id="${cssEscape(providerConnectionId)}"]`,
  )
}

/** PAGE-LEVEL — Modell-Option lebt im portaled Content. */
export function getOption(
  page: Page,
  args: { providerConnectionId: string; modelId: string },
  _picker?: Locator,
): Locator {
  return page.locator(
    `[data-testid="${AiModelPickerTestId.option}"][data-provider-connection-id="${cssEscape(args.providerConnectionId)}"][data-model-id="${cssEscape(args.modelId)}"]`,
  )
}

/**
 * Stage-Row im LlmRouting-Panel (Slice 5.6 final).
 * Selektion via data-testid + data-stage (stabil, kein i18n-Label).
 */
export function getStageRow(page: Page, stage: string): Locator {
  return page.locator(
    `[data-testid="${LlmRoutingTestId.stageRow}"][data-stage="${cssEscape(stage)}"]`,
  )
}

/** AiModelPicker innerhalb einer bestimmten Stage-Row. */
export function getStagePicker(page: Page, stage: string): Locator {
  return getStageRow(page, stage).getByTestId(AiModelPickerTestId.root)
}

/** Action: Picker oeffnen (Fokus/Klick auf Trigger-Input). */
export async function openPicker(page: Page, picker?: Locator): Promise<void> {
  await getPickerInput(page, picker).click()
}

/** Action: Modell per Klick auswaehlen (Picker muss geoeffnet sein). */
export async function selectOptionByClick(
  page: Page,
  args: { providerConnectionId: string; modelId: string },
  _picker?: Locator,
): Promise<void> {
  const option = getOption(page, args)
  await expect(option).toBeVisible()
  await expect(option).toBeEnabled()
  await option.click()
}

/** Action: Tastatur-Drill ↓↓↑Enter. */
export async function drillKeyboard(
  page: Page,
  picker?: Locator,
): Promise<void> {
  const input = getPickerInput(page, picker)
  await input.press('ArrowDown')
  await input.press('ArrowDown')
  await input.press('ArrowUp')
  await input.press('Enter')
}

/** Action: aktuelle Selektion aus dem Trigger-Input lesen. */
export async function readSelectedLabel(
  page: Page,
  picker?: Locator,
): Promise<string> {
  return (await getPickerInput(page, picker).inputValue()).trim()
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

/** CSS.escape-Polyfill fuer Attribut-Selektoren (Doppelpunkt in model_id). */
function cssEscape(value: string): string {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
    return CSS.escape(value)
  }
  return value.replace(/(["\\\]\[])/g, '\\$1')
}