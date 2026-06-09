/* Agora 2026 — icon set as Vue functional components.
   Avoids v-html for SVG injection (security review #482).
   Each icon is a `() => VNode` rendered via <component :is="..." />. */

import { h } from 'vue'
import type { FunctionalComponent } from 'vue'

const STROKE = {
  fill: 'none',
  stroke: 'currentColor',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round',
}

function svg(
  size: number,
  children: ReturnType<typeof h>[],
  viewBox = '0 0 24 24',
  strokeWidth = 1.6,
): ReturnType<typeof h> {
  return h(
    'svg',
    { viewBox, width: size, height: size, 'stroke-width': strokeWidth, ...STROKE },
    children,
  )
}

const Dashboard: FunctionalComponent = () =>
  svg(16, [
    h('rect', { x: 3, y: 3, width: 7, height: 9, rx: 1.5 }),
    h('rect', { x: 14, y: 3, width: 7, height: 5, rx: 1.5 }),
    h('rect', { x: 14, y: 12, width: 7, height: 9, rx: 1.5 }),
    h('rect', { x: 3, y: 16, width: 7, height: 5, rx: 1.5 }),
  ])

const Runs: FunctionalComponent = () =>
  svg(16, [h('path', { d: 'M13 2 4 14h7l-1 8 9-12h-7z' })])

const Projects: FunctionalComponent = () =>
  svg(16, [
    h('path', { d: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z' }),
  ])

const Datasets: FunctionalComponent = () =>
  svg(16, [
    h('ellipse', { cx: 12, cy: 5, rx: 8, ry: 3 }),
    h('path', { d: 'M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5' }),
    h('path', { d: 'M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6' }),
  ])

const Templates: FunctionalComponent = () =>
  svg(16, [
    h('rect', { x: 4, y: 3, width: 16, height: 18, rx: 2 }),
    h('path', { d: 'M8 8h8M8 12h8M8 16h5' }),
  ])

const Monitoring: FunctionalComponent = () =>
  svg(16, [h('path', { d: 'M3 12h4l3-8 4 16 3-8h4' })])

const Settings: FunctionalComponent = () =>
  svg(16, [
    h('circle', { cx: 12, cy: 12, r: 3 }),
    h('path', {
      d: 'M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
    }),
  ])

const Search: FunctionalComponent = () =>
  svg(14, [h('circle', { cx: 11, cy: 11, r: 7 }), h('path', { d: 'm20 20-3.5-3.5' })])

const Bell: FunctionalComponent = () =>
  svg(15, [
    h('path', { d: 'M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9' }),
    h('path', { d: 'M10 21a2 2 0 0 0 4 0' }),
  ])

const Caret: FunctionalComponent = () => svg(12, [h('path', { d: 'm6 9 6 6 6-6' })], '0 0 24 24', 1.8)

const Chevron: FunctionalComponent = () => svg(12, [h('path', { d: 'm9 6 6 6-6 6' })])

const More: FunctionalComponent = () =>
  svg(14, [
    h('circle', { cx: 5, cy: 12, r: 1 }),
    h('circle', { cx: 12, cy: 12, r: 1 }),
    h('circle', { cx: 19, cy: 12, r: 1 }),
  ])

const Plus: FunctionalComponent = () =>
  svg(14, [h('path', { d: 'M12 5v14M5 12h14' })], '0 0 24 24', 1.7)

const Upload: FunctionalComponent = () =>
  svg(
    22,
    [
      h('path', { d: 'M21 15v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3' }),
      h('path', { d: 'M7 9l5-5 5 5' }),
      h('path', { d: 'M12 4v12' }),
    ],
    '0 0 24 24',
    1.4,
  )

const External: FunctionalComponent = () =>
  svg(12, [
    h('path', { d: 'M14 5h5v5' }),
    h('path', { d: 'M19 5l-9 9' }),
    h('path', { d: 'M19 13v6H5V5h6' }),
  ])

const Branch: FunctionalComponent = () =>
  svg(13, [
    h('circle', { cx: 6, cy: 5, r: 2 }),
    h('circle', { cx: 6, cy: 19, r: 2 }),
    h('circle', { cx: 18, cy: 12, r: 2 }),
    h('path', { d: 'M6 7v10M6 12c0-4 3-5 5-5h5' }),
  ])

const Download: FunctionalComponent = () =>
  svg(12, [h('path', { d: 'M12 4v12M7 11l5 5 5-5M5 20h14' })])

const Filter: FunctionalComponent = () =>
  svg(13, [h('path', { d: 'M3 5h18l-7 9v6l-4-2v-4z' })])

export const A26_ICONS: Record<string, FunctionalComponent> = {
  dashboard: Dashboard,
  runs: Runs,
  projects: Projects,
  datasets: Datasets,
  templates: Templates,
  monitoring: Monitoring,
  settings: Settings,
  search: Search,
  bell: Bell,
  caret: Caret,
  chevron: Chevron,
  more: More,
  plus: Plus,
  upload: Upload,
  external: External,
  branch: Branch,
  download: Download,
  filter: Filter,
}

export const A26_PROV_LABEL: Record<string, string> = {
  openai: 'AI',
  ollama: 'OL',
  gemini: 'G',
  anthropic: 'A',
  copilot: 'GH',
  compat: '◇',
}

export const A26_PROV_NAME: Record<string, string> = {
  openai: 'OpenAI',
  ollama: 'Ollama Cloud',
  gemini: 'Gemini',
  anthropic: 'Anthropic',
  copilot: 'GitHub Copilot',
  compat: 'OpenAI-Compatible',
}
