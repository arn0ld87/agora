<script setup lang="ts">
import Shell from '../components/Shell.vue'
import Icon from '../components/Icon.vue'
import ProvMark from '../components/ProvMark.vue'

const emit = defineEmits<{ (e: 'nav', key: string): void }>()

const steps: { n: string; name: string; mdl: string; state: 'inherit' | 'override' }[] = [
  { n: '01', name: 'Ontologie', mdl: 'glm-5.1', state: 'inherit' },
  { n: '02', name: 'Personas', mdl: 'glm-5.1', state: 'inherit' },
  { n: '03', name: 'Simulation', mdl: 'gpt-4o', state: 'override' },
  { n: '04', name: 'Memory', mdl: 'glm-5.1', state: 'inherit' },
  { n: '05', name: 'Report', mdl: 'claude-sonnet-4', state: 'override' },
]

function provFor(mdl: string): string {
  if (mdl.startsWith('gpt')) return 'openai'
  if (mdl.startsWith('claude')) return 'anthropic'
  if (mdl.startsWith('gemini')) return 'gemini'
  return 'ollama'
}

const stats: { label: string; val: string; trend: 'up' | 'down' | 'flat'; delta: string }[] = [
  { label: 'Aktive Runs', val: '34', trend: 'up', delta: '+6 vs gestern' },
  { label: 'Heute fertig', val: '18', trend: 'up', delta: '+3' },
  { label: 'Ø Confidence', val: '0.87', trend: 'flat', delta: 'stabil' },
  { label: 'Personas aktiv', val: '400', trend: 'up', delta: '12 Runs' },
]

function sparkPath(trend: 'up' | 'down' | 'flat'): string {
  if (trend === 'up') return 'M2 18 L10 12 L18 14 L26 6 L34 8 L42 4'
  if (trend === 'flat') return 'M2 12 L10 10 L18 12 L26 11 L34 12 L42 11'
  return 'M2 4 L10 8 L18 6 L26 14 L34 12 L42 16'
}
function sparkColor(trend: 'up' | 'down' | 'flat'): string {
  if (trend === 'up') return 'var(--a26-ok)'
  if (trend === 'down') return 'var(--a26-err)'
  return 'var(--a26-ink-3)'
}
function trendGlyph(trend: 'up' | 'down' | 'flat'): string {
  return trend === 'up' ? '↗' : trend === 'down' ? '↘' : '→'
}
function trendCls(trend: 'up' | 'down' | 'flat'): string {
  return trend
}

const activeRuns = [
  { id: 'run_90ea…bbb', name: 'seed.md', proj: 'DACH · Tech', phase: 'Simulation', dot: 'accent', pct: 85, started: 'vor 2 h' },
  { id: 'run_e330_b42', name: 'mittelstand-ki.pdf', proj: 'proj_5683…bf5b', phase: 'Ontologie', dot: 'warn', pct: 12, started: 'vor 2 h' },
  { id: 'run_4c1f_a91', name: 'sentiment.txt', proj: 'EU · Politik', phase: 'Memory', dot: 'accent', pct: 62, started: 'vor 1 h' },
  { id: 'run_8b2d_0e7', name: 'beta-launch.md', proj: 'Internal · DX', phase: 'Report', dot: 'ok', pct: 96, started: 'vor 18 m' },
  { id: 'run_a30f_19c', name: 'pricing-q3.pdf', proj: 'GTM · DE', phase: 'Personas', dot: 'warn', pct: 34, started: 'vor 12 m' },
]

const sysServices: { name: string; meta: string; status: 'ok' | 'warn' | 'err'; val: string }[] = [
  { name: 'Ollama Cloud', meta: '39 Modelle · 4.2 k ctx', status: 'ok', val: 'erreichbar' },
  { name: 'OpenAI', meta: '10 Modelle · sk-…MLUA', status: 'ok', val: 'erreichbar' },
  { name: 'Google Gemini', meta: 'gemini-2.5-pro · 1 M ctx', status: 'ok', val: 'erreichbar' },
  { name: 'Neo4j', meta: 'graph 6.83 · 412k Knoten', status: 'ok', val: 'erreichbar' },
  { name: 'GitHub Copilot', meta: 'gh CLI · Token gültig', status: 'ok', val: 'gh CLI' },
  { name: 'OpenAI Compatible', meta: 'self-hosted · 30 ms p95', status: 'warn', val: 'Latenz hoch' },
]
</script>

<template>
  <Shell active="dashboard" :crumbs="['Workbench', 'Dashboard']" @nav="emit('nav', $event)">
    <div class="dash-stack" style="max-width: 1280px">
      <div class="a26-page-head">
        <div>
          <div class="a26-kicker" style="margin-bottom: 6px">Workbench</div>
          <h1 class="a26-page-title">Dashboard</h1>
          <div class="a26-page-sub">Aktive Runs, Reports, Systemzustand auf einen Blick.</div>
        </div>
        <div class="a26-page-head-actions">
          <button class="a26-btn"><Icon name="filter" /> Filter</button>
          <button class="a26-btn"><Icon name="branch" /> Branches</button>
          <button class="a26-btn a26-btn-primary"><Icon name="plus" /> Neuer Run</button>
        </div>
      </div>

      <!-- Hero: New Run -->
      <div class="hero">
        <div class="hero-head">
          <div class="hero-title-row">
            <span class="a26-kicker-accent">№ 01 · Neuer Run</span>
          </div>
          <span class="a26-kicker" style="display: inline-flex; align-items: center; gap: 8px">
            <span class="a26-dot ok" />
            backend · neo4j · ollama erreichbar
          </span>
        </div>

        <div class="hero-title" style="margin-bottom: 6px">Quelle ablegen, Vorlage wählen, starten.</div>
        <div class="hero-meta" style="margin-bottom: 22px; max-width: 600px">
          Der Workspace-Default wird automatisch auf alle Schritte angewendet — pro Schritt kannst du
          unten gezielt überschreiben. Keine erneute Eingabe nötig.
        </div>

        <div class="hero-grid">
          <div class="dropzone">
            <div class="dz-icon"><Icon name="upload" /></div>
            <div class="dz-title">Datei hierher ziehen — oder klicken</div>
            <div class="dz-meta">.pdf  ·  .md  ·  .txt  ·  .markdown   bis 25 MB</div>
          </div>

          <div class="field-stack">
            <div class="field">
              <span class="field-label">Vorlage</span>
              <div class="field-row">
                <span>DACH · Tech-Adoption · Reddit + Twitter</span>
                <span class="caret"><Icon name="caret" /></span>
              </div>
            </div>
            <div class="field">
              <span class="field-label">Sprache</span>
              <div class="field-row">
                <span>Deutsch (de-DE)</span>
                <span class="caret"><Icon name="caret" /></span>
              </div>
            </div>
            <div class="field">
              <span class="field-label">Fragestellung *</span>
              <div class="field-area placeholder">
                z. B. „Welche politischen Reaktionen sind in der DACH-Region zu erwarten?"
              </div>
            </div>
          </div>
        </div>

        <!-- Per-step model strip — solves the "re-entering" pain -->
        <div class="steps-strip">
          <div class="ss-explain">
            <strong>Modelle pro Schritt</strong><br />
            Erbt vom Workspace-Default. Klicke auf einen Chip, um nur diesen Schritt zu überschreiben.
          </div>
          <div class="steps-list">
            <div v-for="s in steps" :key="s.n" class="step-chip">
              <span class="num">{{ s.n }}</span>
              <span>{{ s.name }}</span>
              <span class="sep">·</span>
              <span class="mdl">
                <ProvMark :prov="provFor(s.mdl)" />
                <span class="a26-mono">{{ s.mdl }}</span>
              </span>
              <span
                v-if="s.state === 'override'"
                class="a26-kicker"
                style="font-size: 9px; color: var(--a26-warm-ink)"
              >override</span>
            </div>
          </div>
        </div>

        <div style="display: flex; justify-content: flex-end; margin-top: 22px; gap: 10px">
          <button class="a26-btn">Als Vorlage speichern</button>
          <button class="a26-btn a26-btn-accent">Run starten <Icon name="chevron" /></button>
        </div>
      </div>

      <!-- Stats row -->
      <div class="stats">
        <div v-for="(s, i) in stats" :key="i" class="stat">
          <span class="label">{{ s.label }}</span>
          <span class="val a26-tabular">{{ s.val }}</span>
          <span class="trend">
            <span :class="trendCls(s.trend)">{{ trendGlyph(s.trend) }}</span>
            {{ s.delta }}
          </span>
          <svg class="spark" width="44" height="22" viewBox="0 0 44 22" fill="none">
            <path :d="sparkPath(s.trend)" :stroke="sparkColor(s.trend)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </div>

      <!-- Two-column section -->
      <div class="dash-grid">
        <!-- Active runs panel -->
        <div class="panel">
          <div class="panel-head">
            <span class="title">Aktive Runs</span>
            <span class="a26-kicker-accent">{{ activeRuns.length }} live</span>
            <span class="meta">letzte Aktualisierung 12 s</span>
          </div>
          <table class="run-table">
            <thead>
              <tr>
                <th>Run-ID</th><th>Quelle</th><th>Projekt</th>
                <th>Phase</th><th>Fortschritt</th><th>Gestartet</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in activeRuns" :key="r.id">
                <td class="id">{{ r.id }}</td>
                <td class="name">{{ r.name }}</td>
                <td class="id">{{ r.proj }}</td>
                <td>
                  <span class="phase-pill">
                    <span class="a26-dot" :class="r.dot" />
                    {{ r.phase }}
                  </span>
                </td>
                <td>
                  <div style="display: flex; align-items: center; gap: 10px">
                    <div class="progress-bar"><span :style="{ width: r.pct + '%' }" /></div>
                    <span class="a26-mono" style="font-size: 11px; color: var(--a26-ink-2)">{{ r.pct }}%</span>
                  </div>
                </td>
                <td class="id">{{ r.started }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- System health -->
        <div class="panel">
          <div class="panel-head">
            <span class="title">System</span>
            <span class="meta">alle Dienste</span>
          </div>
          <div class="sys-list">
            <div v-for="s in sysServices" :key="s.name" class="sys-row">
              <div>
                <div class="name">{{ s.name }}</div>
                <div class="meta">{{ s.meta }}</div>
              </div>
              <span class="health-pill" :class="s.status">
                <span class="a26-dot" :class="s.status" />
                {{ s.val }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Shell>
</template>

<style scoped>
.dash-stack { display: flex; flex-direction: column; gap: 22px; }

/* Hero */
.hero {
  position: relative;
  background: var(--a26-bg-elevated);
  border: 1px solid var(--a26-line);
  border-radius: var(--a26-r-xl);
  padding: 26px 28px;
  overflow: hidden;
}
.hero::before {
  content: "";
  position: absolute;
  inset: -1px;
  background:
    radial-gradient(60% 100% at 100% 0%, oklch(0.52 0.19 264 / 0.07), transparent 55%),
    radial-gradient(40% 90% at 0% 100%, oklch(0.68 0.14 60 / 0.05), transparent 55%);
  pointer-events: none;
  z-index: 0;
}
.hero > * { position: relative; z-index: 1; }

.hero-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 22px; }
.hero-title-row { display: flex; align-items: baseline; gap: 14px; }
.hero-title {
  font-family: var(--a26-font-display);
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.02em;
  margin: 0;
}
.hero-meta { color: var(--a26-ink-3); font-size: 13px; }

.hero-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 24px; align-items: stretch; }

.dropzone {
  border: 1.5px dashed var(--a26-line-2);
  border-radius: var(--a26-r-lg);
  padding: 36px 24px;
  background:
    repeating-linear-gradient(45deg, oklch(0.985 0.004 80) 0 8px, oklch(0.97 0.005 80) 8px 16px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 10px;
  color: var(--a26-ink-2);
}
.dropzone .dz-icon {
  width: 44px; height: 44px;
  border-radius: 12px;
  background: var(--a26-bg-elevated);
  border: 1px solid var(--a26-line);
  display: grid; place-items: center;
  color: var(--a26-ink-2);
}
.dropzone .dz-title { font-size: 14px; font-weight: 500; color: var(--a26-ink); }
.dropzone .dz-meta { font-family: var(--a26-font-mono); font-size: 10.5px; letter-spacing: 0.04em; color: var(--a26-ink-3); }

.field-stack { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-family: var(--a26-font-mono); font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--a26-ink-3); }
.field-row {
  display: flex;
  align-items: center;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--a26-line);
  border-radius: 8px;
  background: var(--a26-bg-elevated);
  font-size: 13px;
  color: var(--a26-ink);
  gap: 8px;
}
.field-row .caret { margin-left: auto; color: var(--a26-ink-3); }
.field-area {
  min-height: 86px;
  padding: 10px 12px;
  border: 1px solid var(--a26-line);
  border-radius: 8px;
  background: var(--a26-bg-elevated);
  font-size: 13px;
  line-height: 1.5;
  color: var(--a26-ink-2);
}
.field-area.placeholder { color: var(--a26-ink-4); }

/* Per-step model strip */
.steps-strip {
  margin-top: 18px;
  border-top: 1px dashed var(--a26-line);
  padding-top: 18px;
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 18px;
  align-items: start;
}
.steps-strip .ss-explain { font-size: 12px; color: var(--a26-ink-3); line-height: 1.5; }
.steps-strip .ss-explain strong { color: var(--a26-ink); font-weight: 500; }
.steps-list { display: flex; gap: 10px; flex-wrap: wrap; }
.step-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 6px 10px;
  border: 1px solid var(--a26-line);
  border-radius: 999px;
  background: var(--a26-bg-elevated);
  font-size: 12px;
  color: var(--a26-ink-2);
}
.step-chip .num { font-family: var(--a26-font-mono); font-size: 10px; color: var(--a26-ink-3); }
.step-chip .sep { color: var(--a26-ink-4); }
.step-chip .mdl {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px;
  background: var(--a26-bg-sunken);
  border: 1px solid var(--a26-line);
  border-radius: 999px;
}
.step-chip .mdl .a26-mono { font-size: 11px; color: var(--a26-ink); }
.step-chip:hover { border-color: var(--a26-line-strong); }

/* Stats */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
.stat {
  position: relative;
  background: var(--a26-bg-elevated);
  border: 1px solid var(--a26-line);
  border-radius: var(--a26-r-lg);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.stat .label { font-family: var(--a26-font-mono); font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--a26-ink-3); }
.stat .val { font-family: var(--a26-font-display); font-size: 40px; line-height: 1.1; font-weight: 400; letter-spacing: -0.02em; color: var(--a26-ink); }
.stat .trend { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--a26-ink-3); }
.stat .trend .up { color: var(--a26-ok); }
.stat .trend .down { color: var(--a26-err); }
.stat .spark { position: absolute; right: 16px; top: 16px; opacity: 0.7; }

/* Two-column section */
.dash-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 22px; align-items: start; }

.panel {
  background: var(--a26-bg-elevated);
  border: 1px solid var(--a26-line);
  border-radius: var(--a26-r-lg);
  overflow: hidden;
}
.panel-head { display: flex; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--a26-line); }
.panel-head .title { font-size: 13px; font-weight: 500; color: var(--a26-ink); }
.panel-head .meta { margin-left: auto; font-family: var(--a26-font-mono); font-size: 10.5px; color: var(--a26-ink-3); letter-spacing: 0.06em; }

.run-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.run-table th {
  text-align: left;
  font-family: var(--a26-font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--a26-ink-3);
  font-weight: 500;
  padding: 10px 18px;
  border-bottom: 1px solid var(--a26-line);
  background: var(--a26-bg-sunken);
}
.run-table td { padding: 12px 18px; border-bottom: 1px solid var(--a26-line); vertical-align: middle; }
.run-table tr:last-child td { border-bottom: none; }
.run-table tr:hover td { background: var(--a26-bg-sunken); }
.run-table .id { font-family: var(--a26-font-mono); font-size: 11.5px; color: var(--a26-ink-2); }
.run-table .name { color: var(--a26-ink); font-weight: 450; }
.run-table .phase-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 999px;
  border: 1px solid var(--a26-line);
  background: var(--a26-bg-sunken);
  color: var(--a26-ink-2);
}
.run-table .phase-pill .a26-dot { width: 5px; height: 5px; box-shadow: none; }

.progress-bar {
  position: relative;
  height: 5px;
  border-radius: 999px;
  background: var(--a26-line);
  overflow: hidden;
  min-width: 90px;
}
.progress-bar > span {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, var(--a26-accent), var(--a26-accent-2));
  border-radius: 999px;
}

/* System health */
.sys-list { display: flex; flex-direction: column; }
.sys-row { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-bottom: 1px solid var(--a26-line); }
.sys-row:last-child { border-bottom: none; }
.sys-row .name { font-size: 13px; color: var(--a26-ink); font-weight: 450; }
.sys-row .meta { font-family: var(--a26-font-mono); font-size: 10.5px; color: var(--a26-ink-3); letter-spacing: 0.04em; }

.health-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 9px;
  font-size: 11px;
  border-radius: 999px;
  border: 1px solid;
  margin-left: auto;
}
.health-pill.ok { color: var(--a26-ok); border-color: oklch(0.6 0.14 155 / 0.3); background: var(--a26-ok-soft); }
.health-pill.warn { color: var(--a26-warm-ink); border-color: oklch(0.72 0.16 75 / 0.3); background: var(--a26-warn-soft); }
.health-pill.err { color: var(--a26-err); border-color: oklch(0.58 0.2 25 / 0.3); background: var(--a26-err-soft); }
</style>
