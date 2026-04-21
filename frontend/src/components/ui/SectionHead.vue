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
  grid-template-columns: 1fr 2fr;
  gap: var(--s-7);
  align-items: start;
  padding-bottom: var(--s-7);
  border-bottom: 1px solid var(--rule-strong);
}
.left {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.num {
  font-family: var(--ff-serif);
  font-weight: 300;
  font-size: clamp(84px, 10vw, 140px);
  line-height: 0.88;
  letter-spacing: -0.04em;
  color: var(--ink-0);
}
.k {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--accent);
}
h2 {
  font-family: var(--ff-serif);
  font-weight: 400;
  font-size: clamp(32px, 4vw, 52px);
  line-height: 1.1;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--ink-0);
}
.sub {
  font-family: var(--ff-sans);
  font-size: var(--fs-18);
  line-height: 1.6;
  color: var(--fg-body);
  max-width: 54ch;
  margin: var(--s-5) 0 0;
}
@media (max-width: 720px) {
  .section-head { grid-template-columns: 1fr; }
}
</style>
