<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<script setup>
// Routes are defined in src/router/index.js
</script>

<style>
/* Reset only — design tokens live in src/assets/styles/tokens.css
   App-wide layout helpers in src/assets/styles/global.css */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--paper-1);
}

::-webkit-scrollbar-thumb {
  background: var(--ink-2);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--ink-0);
}
</style>
