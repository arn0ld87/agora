<template>
  <div
    v-if="open"
    class="log-drawer"
    role="region"
    :aria-label="t('logs.drawer.title')"
    :style="{ height: drawerHeight + 'px' }"
  >
    <div
      class="resize-handle"
      role="separator"
      aria-orientation="horizontal"
      tabindex="0"
      :aria-label="t('logs.drawer.resize')"
      :aria-valuemin="LOG_DRAWER_MIN_HEIGHT"
      :aria-valuemax="logDrawerMaxHeight()"
      :aria-valuenow="drawerHeight"
      @pointerdown="onHandleDown"
      @keydown="onHandleKey"
    ></div>
    <LogStream :active="open" :title="t('logs.drawer.title')" :scope-id="scopeId">
      <template #actions>
        <button
          class="close-btn"
          :title="t('common.close')"
          :aria-label="t('common.close')"
          @click="$emit('close')"
        >✕</button>
      </template>
    </LogStream>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import LogStream from './activity/LogStream.vue'
import { useLogScope } from '../composables/activity/useLogScope'
import {
  LOG_DRAWER_MIN_HEIGHT,
  logDrawerMaxHeight,
  useLogDrawerHeight,
} from '../composables/useLogDrawer'

defineProps<{ open?: boolean }>()
defineEmits<{ close: [] }>()

const { t } = useI18n()
// In einem geöffneten Lauf ist die Konsole auf diesen Lauf vorgefiltert.
const scopeId = useLogScope()

// Hoehe: Maus (Zeiger am Griff) und Tastatur (Pfeile, Pos1/Ende), gemerkt.
const { height: drawerHeight, setHeight } = useLogDrawerHeight()
const KEY_STEP = 24
let dragStartY = 0
let dragStartHeight = 0

function onHandleMove(e: PointerEvent) {
  setHeight(dragStartHeight + (dragStartY - e.clientY))
}
function onHandleUp() {
  window.removeEventListener('pointermove', onHandleMove)
  window.removeEventListener('pointerup', onHandleUp)
}
function onHandleDown(e: PointerEvent) {
  e.preventDefault()
  dragStartY = e.clientY
  dragStartHeight = drawerHeight.value
  window.addEventListener('pointermove', onHandleMove)
  window.addEventListener('pointerup', onHandleUp)
}
function onHandleKey(e: KeyboardEvent) {
  const step = e.shiftKey ? KEY_STEP * 4 : KEY_STEP
  if (e.key === 'ArrowUp') setHeight(drawerHeight.value + step)
  else if (e.key === 'ArrowDown') setHeight(drawerHeight.value - step)
  else if (e.key === 'Home') setHeight(logDrawerMaxHeight())
  else if (e.key === 'End') setHeight(LOG_DRAWER_MIN_HEIGHT)
  else return
  e.preventDefault()
}

onUnmounted(onHandleUp)
</script>

<style scoped>
.log-drawer {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  background: var(--s1);
  border-top: 1px solid var(--line);
  z-index: 90;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-pop);
  font-family: var(--ag-font-sans);
}
.resize-handle {
  position: absolute;
  top: -4px; left: 0; right: 0;
  height: 9px;
  cursor: ns-resize;
  touch-action: none;
  z-index: 1;
}
.resize-handle::after {
  content: '';
  position: absolute;
  top: 3px; left: 50%;
  width: 36px; height: 3px;
  margin-left: -18px;
  border-radius: var(--ag-r-pill);
  background: var(--s4);
}
.resize-handle:hover::after,
.resize-handle:focus-visible::after { background: var(--acc); }
.resize-handle:focus-visible { outline: 2px solid var(--acc); outline-offset: -2px; }
.close-btn {
  background: transparent;
  border: none;
  color: var(--fg2);
  width: 32px; height: 32px;
  border-radius: var(--ag-r-8);
  cursor: pointer;
  font: inherit;
}
.close-btn:hover { background: var(--s3); color: var(--fg); }
.close-btn:focus-visible { outline: 2px solid var(--acc); outline-offset: 1px; }
</style>
