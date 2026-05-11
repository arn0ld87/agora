<script setup>
defineProps({
  num: { type: [String, Number], required: true },
  kicker: { type: String, default: '' },
  title: { type: String, default: '' },
})
</script>

<template>
  <header class="section-head">
    <div class="left">
      <div class="num">{{ String(num).padStart(2, '0') }}</div>
      <div class="k">№ {{ String(num).padStart(2, '0') }}<template v-if="kicker"> — {{ kicker }}</template></div>
    </div>
    <div class="right">
      <h2 v-if="title">{{ title }}</h2>
      <slot v-else name="title" />
      <p v-if="$slots.sub" class="sub"><slot name="sub" /></p>
    </div>
  </header>
</template>

<style scoped>
/* See global.css .section-head — but scoped variant for nested use */
.section-head {
  display: grid;
  grid-template-columns: minmax(120px, 0.42fr) 1fr;
  gap: var(--sp-7, var(--s-7));
  align-items: start;
  padding-bottom: var(--sp-6, var(--s-6));
  border-bottom: 1px solid var(--hairline-strong, var(--rule-strong));
}
.left {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3, var(--s-3));
}
.num {
  font-family: var(--font-sans, var(--ff-sans));
  font-weight: 600;
  font-size: clamp(42px, 5vw, 72px);
  line-height: 0.95;
  letter-spacing: 0;
  color: var(--text-primary, var(--fg));
  font-variant-numeric: tabular-nums;
}
.k {
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-caption-1, var(--fs-12));
  letter-spacing: 0;
  text-transform: none;
  color: var(--text-secondary, var(--fg-muted));
  font-weight: 600;
}
h2 {
  font-family: var(--font-sans, var(--ff-sans));
  font-weight: 600;
  font-size: clamp(28px, 3vw, 44px);
  line-height: 1.08;
  letter-spacing: 0;
  margin: 0;
  color: var(--text-primary, var(--fg));
}
.sub {
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-body, var(--fs-16));
  line-height: var(--lh-body, 1.55);
  color: var(--text-secondary, var(--fg-body));
  max-width: 54ch;
  margin: var(--sp-4, var(--s-4)) 0 0;
}
@media (max-width: 720px) {
  .section-head { grid-template-columns: 1fr; }
}
</style>
