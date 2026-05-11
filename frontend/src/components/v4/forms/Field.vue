<script setup lang="ts">
defineProps<{
  label: string
}>()
</script>

<template>
  <div class="v4-field">
    <label class="v4-field__label">{{ label }}</label>
    <div class="v4-field__control">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.v4-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.v4-field__label {
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-secondary);
  line-height: 1;
}

.v4-field__control {
  /* Nimmt den vollen Platz; kein extra padding */
}
</style>
