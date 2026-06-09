<script setup lang="ts">
import Shell from '../components/Shell.vue'
import Icon from '../components/Icon.vue'
import ProvMark from '../components/ProvMark.vue'

const emit = defineEmits<{ (e: 'nav', key: string): void }>()

type Row = {
  id: string; file: string; q: string
  status: 'run' | 'ok' | 'warn' | 'err'
  label: string; conf: number | null
  model: string; prov: string
  branch: string; when: string
}

const rows: Row[] = [
  { id: 'run_90ea_a9c1bbb', file: 'seed.md', q: 'Welche Reaktionen auf das KI-Förderpaket?', status: 'run', label: 'Simulation · 85 %', conf: null, model: 'gpt-4o', prov: 'openai', branch: 'main', when: 'vor 2 h' },
  { id: 'run_e330_b42a91c', file: 'mittelstand-ki.pdf', q: 'On-prem-Ticketing — Akzeptanz im KMU?', status: 'run', label: 'Ontologie · 12 %', conf: null, model: 'glm-5.1', prov: 'ollama', branch: 'main', when: 'vor 2 h' },
  { id: 'run_8b2d_0e74301', file: 'beta-launch.md', q: 'Wie reagieren Developer auf v4-Release?', status: 'ok', label: 'fertig', conf: 0.91, model: 'claude-sonnet-4', prov: 'anthropic', branch: 'release/v4', when: 'vor 18 m' },
  { id: 'run_a30f_19c4e2b', file: 'pricing-q3.pdf', q: 'Preisreaktion DACH Mittelstand', status: 'run', label: 'Personas · 34 %', conf: null, model: 'gpt-4o', prov: 'openai', branch: 'main', when: 'vor 12 m' },
  { id: 'run_7d1b_88c0fac', file: 'sentiment.txt', q: 'Sentiment zur EU-AI-Act-Erweiterung', status: 'ok', label: 'fertig', conf: 0.82, model: 'glm-5.1', prov: 'ollama', branch: 'main', when: 'vor 4 h' },
  { id: 'run_2a4e_55bb19f', file: 'press-release.md', q: 'Tech-Press-Resonanz auf Launch', status: 'warn', label: 'paused', conf: 0.71, model: 'gemini-2.5-pro', prov: 'gemini', branch: 'experiment/gemini', when: 'gestern' },
  { id: 'run_f019_77a201d', file: 'roadmap-2026.md', q: 'Adoption-Pfade für Roadmap 2026', status: 'err', label: 'rate-limit', conf: null, model: 'gpt-4o', prov: 'openai', branch: 'main', when: 'gestern' },
  { id: 'run_5cd7_30b884e', file: 'survey-results.pdf', q: 'Was treibt Entscheider in DE?', status: 'ok', label: 'fertig', conf: 0.88, model: 'claude-sonnet-4', prov: 'anthropic', branch: 'main', when: 'vor 2 Tagen' },
  { id: 'run_31fa_92e7b16', file: 'positioning.md', q: 'Wie positioniert sich Wettbewerb?', status: 'ok', label: 'fertig', conf: 0.79, model: 'glm-5.1', prov: 'ollama', branch: 'main', when: 'vor 3 Tagen' },
]

function statusDot(s: Row['status']): string {
  if (s === 'run') return 'accent'
  if (s === 'ok') return 'ok'
  if (s === 'warn') return 'warn'
  return 'err'
}
</script>

<template>
  <Shell active="runs" :crumbs="['Workbench', 'Runs · Verlauf']" @nav="emit('nav', $event)">
    <div class="runs-wrap">
      <div class="a26-page-head" style="padding-bottom: 14px; margin-bottom: 0; border-bottom: none">
        <div>
          <div class="a26-kicker" style="margin-bottom: 6px">Workbench</div>
          <h1 class="a26-page-title">Verlauf</h1>
          <div class="a26-page-sub">Run- und Branch-Historie · alles persistiert, alles rückspulbar.</div>
        </div>
        <div class="a26-page-head-actions">
          <button class="a26-btn"><Icon name="download" /> Export CSV</button>
          <button class="a26-btn"><Icon name="branch" /> Branch-Graph</button>
          <button class="a26-btn a26-btn-primary"><Icon name="plus" /> Neuer Run</button>
        </div>
      </div>

      <!-- Editorial hero band -->
      <div class="runs-hero">
        <div>
          <div class="big a26-tabular">187</div>
          <div class="big-sub">Run-Center · gesamt</div>
        </div>
        <div class="editorial">History, resume, <em>branching</em>.</div>
        <div class="sidekick">
          Graph-Builds, Simulationen und Reports in einer Registry. Pausiere, forke, vergleiche, rolle zurück —
          alles ohne Mausverlust.
        </div>
      </div>

      <!-- Filters -->
      <div class="filters">
        <div class="filter-input">
          <Icon name="search" /> Suche · Run, Projekt, Branch
          <span class="kbd">⌘ F</span>
        </div>
        <div class="filter-select">Projekt · Alle <span class="ct">12</span> <span class="caret"><Icon name="caret" /></span></div>
        <div class="filter-select">Typ · Alle <span class="ct">3</span> <span class="caret"><Icon name="caret" /></span></div>
        <div class="filter-select">Status · Alle <span class="ct">5</span> <span class="caret"><Icon name="caret" /></span></div>
        <div class="filter-select">Branch · main <span class="caret"><Icon name="caret" /></span></div>

        <div class="tabs">
          <button class="on">Alle <span class="ct">187</span></button>
          <button>Aktiv <span class="ct">34</span></button>
          <button>Fertig <span class="ct">126</span></button>
          <button>Fehler <span class="ct">9</span></button>
        </div>
      </div>

      <!-- Big table -->
      <table class="run-list-table">
        <thead>
          <tr>
            <th>Run-ID</th>
            <th>Quelle / Frage</th>
            <th>Status</th>
            <th>Confidence</th>
            <th>Modell</th>
            <th>Branch</th>
            <th>Gestartet</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td class="rid">{{ r.id }}</td>
            <td>
              <div class="src">
                <div class="nm">{{ r.file }}</div>
                <div class="q">„{{ r.q }}"</div>
              </div>
            </td>
            <td>
              <span class="status" :class="r.status">
                <span class="a26-dot" :class="statusDot(r.status)" />
                {{ r.label }}
              </span>
            </td>
            <td>
              <div v-if="r.conf != null" class="conf">
                <span class="v a26-tabular">{{ r.conf.toFixed(2) }}</span>
                <span class="bar"><span :style="{ width: r.conf * 100 + '%' }" /></span>
              </div>
              <span v-else style="color: var(--a26-ink-4)">—</span>
            </td>
            <td>
              <span class="mdl"><ProvMark :prov="r.prov" />{{ r.model }}</span>
            </td>
            <td>
              <span class="branch"><Icon name="branch" /><span class="b-name">{{ r.branch }}</span></span>
            </td>
            <td class="when">{{ r.when }}</td>
            <td class="actions">
              <button class="a26-btn a26-btn-sm a26-btn-ghost"><Icon name="external" /></button>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="runs-foot">
        <span>9 von 187 Runs</span>
        <div class="pages">
          <button>‹</button>
          <button class="on">1</button>
          <button>2</button>
          <button>3</button>
          <button>…</button>
          <button>21</button>
          <button>›</button>
        </div>
      </div>
    </div>
  </Shell>
</template>

<style scoped>
.runs-wrap { max-width: 1280px; }

.runs-hero {
  display: grid;
  grid-template-columns: 240px 1fr auto;
  gap: 30px;
  padding: 12px 0 30px;
  border-bottom: 1px solid var(--a26-line);
  margin-bottom: 24px;
  align-items: end;
}
.runs-hero .big {
  font-family: var(--a26-font-display);
  font-size: 120px;
  line-height: 0.95;
  letter-spacing: -0.04em;
  color: var(--a26-ink);
  font-feature-settings: "ss01";
}
.runs-hero .big-sub {
  margin-top: 8px;
  font-family: var(--a26-font-mono);
  font-size: 10.5px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--a26-accent-ink);
}
.runs-hero .editorial {
  font-family: var(--a26-font-display);
  font-size: 56px;
  line-height: 1.04;
  letter-spacing: -0.025em;
  color: var(--a26-ink);
  text-wrap: balance;
  max-width: 18ch;
}
.runs-hero .editorial em { color: var(--a26-accent); font-style: normal; }
.runs-hero .sidekick { color: var(--a26-ink-3); font-size: 13px; line-height: 1.55; max-width: 280px; }

.filters { display: flex; gap: 10px; margin-bottom: 18px; flex-wrap: wrap; align-items: center; }
.filter-input {
  display: flex; align-items: center; gap: 8px;
  height: 36px; padding: 0 12px;
  border: 1px solid var(--a26-line); border-radius: 8px; background: var(--a26-bg-elevated);
  color: var(--a26-ink-2); font-size: 12.5px;
  min-width: 220px;
}
.filter-input .kbd {
  margin-left: auto; font-family: var(--a26-font-mono); font-size: 10px;
  color: var(--a26-ink-3); border: 1px solid var(--a26-line);
  padding: 1px 5px; border-radius: 4px;
}
.filter-select {
  display: flex; align-items: center; gap: 10px;
  height: 36px; padding: 0 12px;
  border: 1px solid var(--a26-line); border-radius: 8px; background: var(--a26-bg-elevated);
  color: var(--a26-ink-2); font-size: 12.5px;
  cursor: pointer;
}
.filter-select .caret { color: var(--a26-ink-3); }
.filter-select .ct { font-family: var(--a26-font-mono); font-size: 10px; color: var(--a26-ink-3); margin-left: 4px; }

.tabs {
  display: inline-flex;
  border: 1px solid var(--a26-line);
  border-radius: 8px;
  overflow: hidden;
  background: var(--a26-bg-elevated);
  margin-left: auto;
}
.tabs button {
  height: 36px;
  padding: 0 14px;
  border: none;
  background: transparent;
  font-size: 12.5px;
  color: var(--a26-ink-2);
  cursor: pointer;
  font-weight: 450;
  display: inline-flex; align-items: center; gap: 7px;
  font-family: inherit;
}
.tabs button.on { background: var(--a26-ink); color: white; }
.tabs button .ct { font-family: var(--a26-font-mono); font-size: 10px; opacity: 0.7; }

.run-list-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--a26-bg-elevated);
  border: 1px solid var(--a26-line);
  border-radius: var(--a26-r-lg);
  overflow: hidden;
}
.run-list-table th {
  text-align: left;
  font-family: var(--a26-font-mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--a26-ink-3);
  font-weight: 500;
  padding: 12px 20px;
  border-bottom: 1px solid var(--a26-line);
  background: var(--a26-bg-sunken);
}
.run-list-table td {
  padding: 14px 20px;
  border-bottom: 1px solid var(--a26-line);
  vertical-align: middle;
}
.run-list-table tr:last-child td { border-bottom: none; }
.run-list-table tr:hover td { background: oklch(0.99 0.005 80); }

.run-list-table .rid { font-family: var(--a26-font-mono); font-size: 11.5px; color: var(--a26-ink-2); }
.run-list-table .src { display: flex; flex-direction: column; gap: 3px; }
.run-list-table .src .nm { font-size: 13.5px; color: var(--a26-ink); font-weight: 450; }
.run-list-table .src .q {
  font-size: 11.5px; color: var(--a26-ink-3);
  max-width: 32ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.run-list-table .status {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 3px 9px;
  font-size: 11px;
  font-family: var(--a26-font-mono);
  letter-spacing: 0.04em;
  border-radius: 999px;
  border: 1px solid var(--a26-line);
  color: var(--a26-ink-2);
  background: var(--a26-bg-sunken);
}
.run-list-table .status.run { color: var(--a26-accent-ink); background: var(--a26-accent-soft); border-color: oklch(0.52 0.19 264 / 0.2); }
.run-list-table .status.ok { color: var(--a26-ok); background: var(--a26-ok-soft); border-color: oklch(0.6 0.14 155 / 0.2); }
.run-list-table .status.warn { color: oklch(0.5 0.14 75); background: var(--a26-warn-soft); border-color: oklch(0.72 0.16 75 / 0.25); }
.run-list-table .status.err { color: var(--a26-err); background: var(--a26-err-soft); border-color: oklch(0.58 0.2 25 / 0.25); }

.run-list-table .conf { display: flex; align-items: center; gap: 9px; }
.run-list-table .conf .v { font-family: var(--a26-font-display); font-size: 22px; line-height: 1; color: var(--a26-ink); }
.run-list-table .conf .bar {
  width: 60px; height: 4px;
  border-radius: 999px; background: var(--a26-line);
  position: relative; overflow: hidden;
}
.run-list-table .conf .bar > span {
  position: absolute; inset: 0; right: auto;
  background: linear-gradient(90deg, var(--a26-accent), var(--a26-accent-2));
}

.run-list-table .mdl {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 8px;
  background: var(--a26-bg-sunken);
  border: 1px solid var(--a26-line);
  border-radius: 6px;
  font-family: var(--a26-font-mono);
  font-size: 10.5px;
  color: var(--a26-ink-2);
}
.run-list-table .branch {
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--a26-font-mono); font-size: 10.5px;
  color: var(--a26-ink-3);
}
.run-list-table .branch .b-name { color: var(--a26-ink-2); }
.run-list-table .when { font-family: var(--a26-font-mono); font-size: 11px; color: var(--a26-ink-3); white-space: nowrap; }
.run-list-table .actions { text-align: right; }

.runs-foot {
  display: flex; align-items: center; gap: 10px;
  margin-top: 14px;
  font-family: var(--a26-font-mono); font-size: 11px; color: var(--a26-ink-3);
}
.runs-foot .pages { margin-left: auto; display: flex; gap: 4px; }
.runs-foot .pages button {
  width: 28px; height: 28px;
  border: 1px solid var(--a26-line);
  background: var(--a26-bg-elevated);
  color: var(--a26-ink-2);
  border-radius: 6px;
  font-family: var(--a26-font-mono);
  font-size: 11px;
  cursor: pointer;
}
.runs-foot .pages button.on { background: var(--a26-ink); color: white; border-color: var(--a26-ink); }
</style>
