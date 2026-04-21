<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getSimulationHistory } from '../api/simulation.js'

const { t, locale } = useI18n()
const router = useRouter()

const projects = ref([])
const loading = ref(true)
const search = ref('')

// Backend returns:
//   { success: true, data: [...simulations], count: N }
// where each item has at least: simulation_id, project_id, simulation_requirement,
// created_at, current_round, total_rounds, runner_status, report_id.
function extractList(payload) {
  const d = payload?.data
  if (Array.isArray(d)) return d
  if (Array.isArray(d?.projects)) return d.projects
  if (Array.isArray(d?.simulations)) return d.simulations
  if (Array.isArray(payload)) return payload
  return []
}

onMounted(async () => {
  try {
    const res = await getSimulationHistory()
    const list = res?.success ? extractList(res) : []
    projects.value = list.slice().sort((a, b) => {
      const ta = new Date(a.created_at || a.updated_at || 0).getTime()
      const tb = new Date(b.created_at || b.updated_at || 0).getTime()
      return tb - ta
    })
  } catch (e) {
    console.error('Failed to load history:', e)
  } finally {
    loading.value = false
  }
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return projects.value
  return projects.value.filter((p) => {
    return (p.simulation_requirement || '').toLowerCase().includes(q) ||
      (p.simulation_id || '').toLowerCase().includes(q)
  })
})

function openProject(p) {
  if (p.simulation_id) {
    router.push({ name: 'Simulation', params: { simulationId: p.simulation_id } })
  } else if (p.project_id) {
    router.push({ name: 'Process', params: { projectId: p.project_id } })
  }
}

function shortId(id) {
  if (!id) return '—'
  return id.replace(/^sim_/, '').slice(0, 8)
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(locale.value === 'de' ? 'de-DE' : 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  })
}

function progressLabel(p) {
  const cur = p.current_round ?? 0
  const tot = p.total_rounds ?? 0
  if (!tot) return t('common.ready')
  if (cur >= tot) return t('common.completed')
  return `${cur} / ${tot}`
}
</script>

<template>
  <div class="history">
    <div class="section-head">
      <div class="left">
        <div class="num">06</div>
        <div class="k">{{ t('history.kicker') }}</div>
      </div>
      <div>
        <h2>{{ t('history.title') }}</h2>
        <input
          v-model="search"
          class="search"
          type="search"
          :placeholder="t('history.search')"
        />
      </div>
    </div>

    <div v-if="loading" class="empty meta">{{ t('common.loading') }}</div>
    <div v-else-if="!filtered.length" class="empty meta">{{ t('history.empty') }}</div>

    <ul v-else class="rows">
      <li v-for="(p, i) in filtered" :key="p.simulation_id || i">
        <a class="row" @click="openProject(p)">
          <span class="idx">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="title">
            {{ p.simulation_requirement || p.title || shortId(p.simulation_id) }}
            <span class="sub">{{ shortId(p.simulation_id) }}</span>
          </span>
          <span class="meta">{{ progressLabel(p) }}</span>
          <span class="yr">{{ formatDate(p.created_at) }}</span>
        </a>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.history { padding-top: var(--s-7); }
.empty {
  padding: var(--s-7) 0;
  text-align: left;
}
.search {
  width: 100%;
  margin-top: var(--s-5);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  padding: var(--s-3) 0;
  font-family: var(--ff-sans);
  font-size: var(--fs-18);
  color: var(--ink-0);
  outline: none;
}
.search:focus { border-bottom-color: var(--accent); }

.rows {
  list-style: none;
  margin: var(--s-7) 0 0;
  padding: 0;
}
.row {
  display: grid;
  grid-template-columns: 56px 1fr 120px 120px;
  gap: var(--s-5);
  align-items: baseline;
  padding: var(--s-5) 0;
  border-top: 1px solid var(--rule);
  cursor: pointer;
  text-decoration: none;
  color: inherit;
  transition: background 160ms ease, padding-left 160ms ease;
}
.rows li:last-child .row { border-bottom: 1px solid var(--rule); }
.row:hover {
  background: var(--paper-1);
  padding-left: var(--s-3);
}
.row .idx {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
}
.row .title {
  font-family: var(--ff-serif);
  font-weight: 400;
  font-size: var(--fs-24);
  line-height: 1.2;
  letter-spacing: -0.005em;
  color: var(--ink-0);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.row .title .sub {
  display: block;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-top: var(--s-2);
}
.row .meta {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-body);
}
.row .yr {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  text-align: right;
}

@media (max-width: 720px) {
  .row { grid-template-columns: 32px 1fr; }
  .row .meta, .row .yr { display: none; }
}
</style>
