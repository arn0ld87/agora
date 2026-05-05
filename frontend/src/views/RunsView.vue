<script setup lang="ts">
import { useRouter } from 'vue-router'
import RunsDashboard from '../components/RunsDashboard.vue'
import AppFooter from '../components/AppFooter.vue'
import AgoraGlyph from '../components/ui/AgoraGlyph.vue'

const router = useRouter()

function goHome(): void {
  void router.push('/')
}
</script>

<template>
  <div class="page">
    <header class="brand">
      <button class="brand-link" type="button" @click="goHome">
        <AgoraGlyph class="brand-glyph" />
        <span class="brand-name">Agora</span>
      </button>
      <nav class="brand-nav">
        <button class="nav-link" type="button" @click="goHome">← Startseite</button>
      </nav>
    </header>

    <main class="main">
      <section class="section">
        <RunsDashboard />
      </section>
    </main>

    <AppFooter />
  </div>
</template>

<style scoped>
.page {
  background: transparent;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-5) var(--s-7);
  border-bottom: 1px solid var(--rule);
}
.brand-link {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  background: transparent;
  border: 0;
  cursor: pointer;
  color: var(--fg);
}
.brand-glyph { width: 28px; height: 28px; }
.brand-name {
  font-family: var(--ff-serif);
  font-size: 22px;
  letter-spacing: -0.01em;
}
.brand-nav { display: flex; gap: var(--s-3); }
.nav-link {
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--rule-strong);
  color: var(--fg);
  padding: 8px 14px;
  cursor: pointer;
}
.nav-link:hover { background: var(--bg-elevated); }
.main { flex: 1; padding: 0 var(--s-7); }
</style>
