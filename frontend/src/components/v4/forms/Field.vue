<script setup lang="ts">
defineProps<{
  label: string
}>()
</script>

<template>
  <label class="v4-field">
    <span class="v4-field__label">{{ label }}</span>
    <span class="v4-field__control">
      <slot />
    </span>
  </label>
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
  color: var(--text-primary);
  line-height: 1;
}

.v4-field__control {
  /* Nimmt den vollen Platz; kein extra padding */
}
</style>
