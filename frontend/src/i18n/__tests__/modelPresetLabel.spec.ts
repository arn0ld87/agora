/**
 * modelPresetLabel — Aufloesungskette der Preset-Anzeigetexte (Issue #1290).
 *
 * Getestete Contracts:
 *   1. `label_key` mit vorhandener Uebersetzung → uebersetzter Text.
 *   2. `label_key` ohne Katalog-Eintrag (te() sagt nein) → Fallback.
 *   3. `label_key` ohne Katalog-Eintrag und ohne te() → Key-Gleichheits-Fallback.
 *   4. Kein `label_key` → Legacy-`label`, sonst `name`.
 *   5. Die realen `llm.preset.*`-Keys aus dem Backend-Vertrag loesen in
 *      de.json und en.json auf echte, verschiedene Texte auf.
 */

import { describe, it, expect, vi } from 'vitest'
import { resolvePresetLabel } from '../modelPresetLabel'
import de from '../locales/de.json'
import en from '../locales/en.json'

// Minimaler t()-Stub mit echtem Katalog-Verhalten: Treffer → Text, Miss → Key.
function makeT(catalog: Record<string, string>) {
  return (key: string): string => catalog[key] ?? key
}

function makeTe(catalog: Record<string, string>) {
  return (key: string): boolean => key in catalog
}

const CATALOG = {
  'llm.preset.ollama.qwen2_5_14b': 'Qwen 2.5 14B (local, low VRAM)',
}

describe('resolvePresetLabel', () => {
  it('Case 1 — label_key mit Katalog-Eintrag gewinnt gegen label und name', () => {
    const label = resolvePresetLabel(
      {
        name: 'qwen2.5:14b',
        label: 'Qwen 2.5 14B (lokal, GPU-arm)',
        label_key: 'llm.preset.ollama.qwen2_5_14b',
      },
      makeT(CATALOG),
      makeTe(CATALOG),
    )
    expect(label).toBe('Qwen 2.5 14B (local, low VRAM)')
  })

  it('Case 2 — unbekannter label_key: te() blockt den Lookup, Fallback auf label', () => {
    const t = vi.fn(makeT(CATALOG))
    const label = resolvePresetLabel(
      { name: 'foo:1b', label: 'Foo 1B', label_key: 'llm.preset.ollama.unbekannt' },
      t,
      makeTe(CATALOG),
    )
    expect(label).toBe('Foo 1B')
    // te() hat den Miss abgefangen — t() wird fuer den Key gar nicht erst gerufen.
    expect(t).not.toHaveBeenCalled()
  })

  it('Case 3 — unbekannter label_key ohne te(): Key-Gleichheit erkennt den Miss', () => {
    const label = resolvePresetLabel(
      { name: 'foo:1b', label_key: 'llm.preset.ollama.unbekannt' },
      makeT(CATALOG),
    )
    expect(label).toBe('foo:1b')
  })

  it('Case 4 — ohne label_key: label, sonst name', () => {
    expect(resolvePresetLabel({ name: 'bar:7b', label: 'Bar 7B' }, makeT(CATALOG))).toBe('Bar 7B')
    expect(resolvePresetLabel({ name: 'bar:7b' }, makeT(CATALOG))).toBe('bar:7b')
  })

  it('Case 5 — die Keys des Backend-Vertrags loesen in beiden Locales auf', () => {
    // Gespiegelt aus backend/app/config.py::Config.LLM_MODEL_PRESETS.
    // Der Drift-Waechter gegen die Backend-Liste selbst sitzt in
    // backend/tests/api/test_model_preset_label_keys.py.
    const keys = [
      'llm.preset.cloud.qwen3_coder_next',
      'llm.preset.ollama.qwen2_5_32b',
      'llm.preset.ollama.qwen2_5_14b',
      'llm.preset.ollama.llama3_1_8b',
      'llm.preset.ollama.gpt_oss_20b',
      'llm.preset.bedrock.gpt_oss_120b',
      'llm.preset.bedrock.qwen3_235b_a22b_2507',
      'llm.preset.bedrock.minimax_m2_5',
      'llm.preset.bedrock.devstral_2_123b',
      'llm.preset.bedrock.nemotron_super_3_120b',
      'llm.preset.bedrock.glm_4_7_flash',
    ]

    function lookup(catalog: unknown, key: string): unknown {
      return key
        .split('.')
        .reduce<unknown>(
          (acc, part) =>
            acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[part] : undefined,
          catalog,
        )
    }

    for (const key of keys) {
      const deVal = lookup(de, key)
      const enVal = lookup(en, key)
      expect(typeof deVal, `de.json fehlt ${key}`).toBe('string')
      expect(typeof enVal, `en.json fehlt ${key}`).toBe('string')
      expect((deVal as string).length).toBeGreaterThan(0)
      expect((enVal as string).length).toBeGreaterThan(0)
    }

    // Mindestens die Ollama-Presets tragen sprachabhaengige Zusaetze —
    // waeren de und en durchweg identisch, haette das Uebersetzen keinen Sinn.
    expect(lookup(de, 'llm.preset.ollama.qwen2_5_14b')).not.toBe(
      lookup(en, 'llm.preset.ollama.qwen2_5_14b'),
    )
  })
})
