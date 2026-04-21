<script setup>
defineProps({
  strong: { type: Boolean, default: false },
})
</script>

<template>
  <hr class="hairline" :class="{ 'hairline--strong': strong }">
</template>

<style scoped>
.hairline {
  border: 0;
  border-top: 1px solid var(--rule);
  margin: 0;
}
.hairline--strong { border-top-color: var(--rule-strong); }
</style>
