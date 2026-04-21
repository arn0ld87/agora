<script setup>
defineProps({
  variant: { type: String, default: 'primary' },
  type: { type: String, default: 'button' },
  disabled: { type: Boolean, default: false },
  arrow: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="btn"
    :class="[`btn--${variant}`, { 'is-loading': loading }]"
  >
    <slot />
    <span v-if="arrow" class="arrow">→</span>
    <span v-if="loading" class="spinner" aria-hidden="true" />
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--s-3);
  padding: 14px 20px;
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  font-weight: 500;
  line-height: 1;
  border-radius: var(--r-1);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
  text-decoration: none;
  white-space: nowrap;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn--primary { background: var(--ink-0); color: var(--paper-0); }
.btn--primary:hover:not(:disabled) { background: var(--accent); color: var(--accent-ink); }

.btn--secondary { background: transparent; color: var(--ink-0); border-color: var(--ink-0); }
.btn--secondary:hover:not(:disabled) { background: var(--ink-0); color: var(--paper-0); }

.btn--ghost { background: transparent; color: var(--ink-0); border-color: var(--rule); padding: 12px 16px; }
.btn--ghost:hover:not(:disabled) { border-color: var(--ink-0); }

.btn--accent { background: var(--accent); color: var(--accent-ink); }
.btn--accent:hover:not(:disabled) { background: var(--ink-0); color: var(--accent); }

.btn--danger { background: transparent; color: #b00020; border-color: #b00020; }
.btn--danger:hover:not(:disabled) { background: #b00020; color: var(--paper-0); }

.btn .arrow { font-family: var(--ff-mono); font-weight: 400; }

.spinner {
  width: 12px;
  height: 12px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: btn-spin 0.7s linear infinite;
}
@keyframes btn-spin { to { transform: rotate(360deg); } }
</style>
