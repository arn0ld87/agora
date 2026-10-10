<template>
  <nav class="breadcrumbs" aria-label="Breadcrumb">
    <ol class="breadcrumbs__list">
      <template v-for="(crumb, idx) in resolvedCrumbs" :key="crumb.to ?? crumb.label">
        <li
          v-if="idx > 0"
          class="breadcrumbs__sep"
          aria-hidden="true"
        >/</li>
        <li
          class="breadcrumbs__item"
          :class="{ 'breadcrumbs__item--last': idx === resolvedCrumbs.length - 1 }"
          data-crumb
          :aria-current="idx === resolvedCrumbs.length - 1 ? 'page' : undefined"
        ><RouterLink
          v-if="idx !== resolvedCrumbs.length - 1 && crumb.to"
          :to="crumb.to"
          class="breadcrumbs__link"
        >{{ crumb.label }}</RouterLink><template v-else>{{ crumb.label }}</template><button
          v-if="crumb.ident"
          type="button"
          class="breadcrumbs__ident"
          data-testid="breadcrumb-ident"
          :aria-label="t('topbar.copyIdent', { ident: crumb.ident })"
          :title="t('topbar.copyIdent', { ident: crumb.ident })"
          @click="copyIdent(crumb.ident)"
        >{{ crumb.ident }}</button></li>
      </template>
    </ol>
    <span class="breadcrumbs__status" aria-live="polite" aria-atomic="true" data-testid="breadcrumb-status">{{ copyStatus }}</span>
  </nav>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

// Legacy interface — exported for Topbar.vue / AppShell.vue backward compatibility
export interface BreadcrumbItem {
  label: string
  path?: string
  /** Technische Kennung (sim_…, report_…, proj_…): erscheint als kleine,
   *  kopierbare Marke neben dem Titel. */
  ident?: string
}

interface InternalCrumb {
  label: string
  to?: string
  ident?: string
}

const props = withDefaults(
  defineProps<{
    /** @deprecated Übergib stattdessen 'items' oder lass Auto-Derive laufen */
    crumbs?: BreadcrumbItem[]
    /** Explizite Liste — überschreibt Auto-Derive aus route.matched */
    items?: InternalCrumb[]
  }>(),
  { crumbs: () => [], items: undefined },
)

const route = useRoute()
const { t, te } = useI18n()

/** Auto-derived crumbs from route.matched using nav.* i18n keys */
const derivedCrumbs = computed<InternalCrumb[]>(() =>
  route.matched
    .filter((r) => r.name !== undefined)
    .map((r) => {
      const name = String(r.name!)
      const key = `nav.${name}`
      return { label: te(key) ? t(key) : name, to: r.path }
    }),
)

/** Final crumb list: items > crumbs (legacy) > auto-derive */
const resolvedCrumbs = computed<InternalCrumb[]>(() => {
  if (props.items) return props.items
  if (props.crumbs && props.crumbs.length > 0) {
    return props.crumbs.map((c) => ({ label: c.label, to: c.path, ident: c.ident }))
  }
  return derivedCrumbs.value
})

/** Rueckmeldung fuer Screenreader (role=status) und Sehende (kurzer Text). */
const copyStatus = ref('')
let statusTimer: ReturnType<typeof setTimeout> | null = null

async function copyIdent(ident: string): Promise<void> {
  let ok: boolean
  try {
    await navigator.clipboard.writeText(ident)
    ok = true
  } catch {
    ok = false
  }
  copyStatus.value = ok ? t('topbar.identCopied') : t('topbar.identCopyFailed')
  if (statusTimer !== null) clearTimeout(statusTimer)
  statusTimer = setTimeout(() => {
    copyStatus.value = ''
    statusTimer = null
  }, 2500)
}
</script>

<style scoped>
.breadcrumbs {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  color: var(--text-secondary);
}

.breadcrumbs__list {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  list-style: none;
  margin: 0;
  padding: 0;
}

.breadcrumbs__sep {
  color: var(--text-quaternary);
  font-weight: 400;
}

.breadcrumbs__item {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-weight: 500;
}

.breadcrumbs__item--last {
  color: var(--text-primary);
  font-weight: 600;
}

.breadcrumbs__link {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
  color: inherit;
  text-decoration: none;
}

.breadcrumbs__link:hover {
  text-decoration: underline;
}

.breadcrumbs__ident {
  max-width: 16ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: 8px;
  padding: 1px 6px;
  border: 0;
  border-radius: var(--ag-r-6, 6px);
  background: var(--s2, transparent);
  color: var(--fg3, var(--text-secondary));
  font-family: var(--ag-font-mono, var(--font-mono));
  font-size: 11px;
  font-weight: 400;
  cursor: pointer;
}

.breadcrumbs__ident:hover {
  background: var(--s3, var(--surface-hover));
  color: var(--fg, var(--text-primary));
}

.breadcrumbs__ident:focus-visible {
  outline: 2px solid var(--acc, var(--accent));
  outline-offset: 2px;
}

.breadcrumbs__status {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.breadcrumbs__link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 2px;
}
</style>
