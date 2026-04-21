<script setup>
import { useI18n } from 'vue-i18n'
import { setLocale, currentLocale } from '../i18n'
import { computed } from 'vue'

const { t } = useI18n()
const locale = computed(() => currentLocale())

function pick(loc) { setLocale(loc) }
</script>

<template>
  <footer class="footer shell">
    <div class="col">
      <div class="brand-line">{{ t('home.footer.credit') }}</div>
      <div class="author-line">
        {{ t('home.footer.by') }}
        <a href="https://alexle135.de" target="_blank" rel="noopener noreferrer" class="author">
          {{ t('home.footer.byName') }}
        </a>
        ·
        <a href="https://alexle135.de" target="_blank" rel="noopener noreferrer">
          {{ t('home.footer.bySite') }} ↗
        </a>
      </div>
      <div>{{ t('home.footer.fork') }} · {{ t('home.footer.license') }}</div>
    </div>
    <div class="col">
      <a href="https://github.com/nikmcfly/Agora" target="_blank" rel="noopener">
        {{ t('home.footer.code') }} ↗
      </a>
      <a href="http://localhost:7474" target="_blank" rel="noopener">Neo4j Browser ↗</a>
    </div>
    <div class="col" style="align-items: flex-end; text-align: right;">
      <span>{{ t('common.language') }}</span>
      <span class="lang-switch">
        <button :class="{ active: locale === 'de' }" @click="pick('de')">DE</button>
        <span>·</span>
        <button :class="{ active: locale === 'en' }" @click="pick('en')">EN</button>
      </span>
    </div>
  </footer>
</template>

<style scoped>
.author-line {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.author-line a {
  color: var(--ink-0);
  text-decoration: none;
  border-bottom: 1px solid var(--accent);
  padding-bottom: 1px;
}
.author-line a:hover { color: var(--accent); }
.author-line a.author { font-family: var(--ff-serif); font-style: italic; font-weight: 400; font-size: 14px; letter-spacing: 0; text-transform: none; }
</style>
