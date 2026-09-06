/**
 * Re-Export der zentralen testIds aus `src/contracts/testIds.ts`.
 *
 * E2E-Specs und Helper importieren von `./testIds`, damit die
 * Importpfade in tests/e2e/ kompakt bleiben. Die Quelle der Wahrheit
 * ist und bleibt `src/contracts/testIds.ts` — wenn dieser Re-Export
 * divergiert, faengt das TypeScript-Compiler-Error.
 *
 * Hinweis: `tsconfig.playwright.json` definiert KEINEN `@/`-Pfad-Alias
 * (paths: {} ueberschreibt das Parent-tsconfig), darum hier ein
 * relativer Import. Wer den `@/`-Alias auch fuer Playwright haben
 * moechte, kann tsconfig.playwright.json erweitern — siehe
 * PR-Diskussion zu #701.
 *
 * `export { AiModelPickerTestId } from '...'` re-exportiert sowohl den
 * Const-Wert als auch den同名 type — daher KEIN zusaetzliches
 * `export type { ... }` (wuerde TS2300 Duplicate identifier werfen).
 */
export {
  AiModelPickerTestId,
  LlmRoutingTestId,
  ReportReaderTestId,
} from '../../../src/contracts/testIds'
