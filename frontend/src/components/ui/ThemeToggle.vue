<script setup>
import { useTheme } from '../../composables/useTheme'

const { theme, setTheme } = useTheme()
</script>

<template>
  <div class="theme-pill" role="group" aria-label="Theme">
    <button
      type="button"
      class="theme-pill__btn"
      :class="{ 'is-on': theme === 'light' }"
      :aria-pressed="theme === 'light'"
      @click="setTheme('light')"
    >
      <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
        <circle cx="12" cy="12" r="4" fill="currentColor" />
        <g stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <line x1="12" y1="2" x2="12" y2="5" />
          <line x1="12" y1="19" x2="12" y2="22" />
          <line x1="2" y1="12" x2="5" y2="12" />
          <line x1="19" y1="12" x2="22" y2="12" />
          <line x1="4.5" y1="4.5" x2="6.5" y2="6.5" />
          <line x1="17.5" y1="17.5" x2="19.5" y2="19.5" />
          <line x1="4.5" y1="19.5" x2="6.5" y2="17.5" />
          <line x1="17.5" y1="6.5" x2="19.5" y2="4.5" />
        </g>
      </svg>
      Light
    </button>
    <button
      type="button"
      class="theme-pill__btn"
      :class="{ 'is-on': theme === 'dark' }"
      :aria-pressed="theme === 'dark'"
      @click="setTheme('dark')"
    >
      <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
        <path
          d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"
          fill="currentColor"
        />
      </svg>
      Dark
    </button>
  </div>
</template>

<style scoped>
.theme-pill {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--bg-glass);
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
  backdrop-filter: blur(12px) saturate(160%);
  -webkit-backdrop-filter: blur(12px) saturate(160%);
}

.theme-pill__btn {
  background: transparent;
  border: 0;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  cursor: pointer;
  color: var(--fg-muted);
  font-family: var(--ff-mono);
  font-size: var(--fs-11);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.theme-pill__btn:hover { color: var(--fg); }

.theme-pill__btn.is-on {
  background: var(--bg-elevated);
  color: var(--fg);
  box-shadow: var(--shadow-1);
}

.theme-pill__btn svg {
  width: 12px;
  height: 12px;
}
</style>
