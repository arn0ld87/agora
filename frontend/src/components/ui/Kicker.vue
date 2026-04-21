<script setup>
defineProps({
  num: { type: [String, Number], default: null },
  accent: { type: Boolean, default: false },
})
</script>

<template>
  <div class="kicker" :class="{ 'kicker--accent': accent }">
    <span v-if="num !== null" class="kicker-num">№ {{ num }} —</span>
    <span class="kicker-text"><slot /></span>
  </div>
</template>

<style scoped>
.kicker {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  line-height: var(--lh-mono);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  display: inline-flex;
  gap: var(--s-2);
  align-items: baseline;
}
.kicker--accent { color: var(--accent); }
.kicker-num { font-weight: 500; }
</style>
