<script setup>
defineProps({
  showGrain: { type: Boolean, default: true },
})
</script>

<template>
  <div class="aurora" aria-hidden="true">
    <span class="aurora__blob aurora__blob--1"></span>
    <span class="aurora__blob aurora__blob--2"></span>
    <span class="aurora__blob aurora__blob--3"></span>
    <span class="aurora__blob aurora__blob--4"></span>
  </div>
  <div v-if="showGrain" class="grain" aria-hidden="true"></div>
</template>

<style scoped>
.aurora {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.aurora__blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: var(--mesh-alpha);
  animation: aurora-float 22s ease-in-out infinite;
}

.aurora__blob--1 {
  width: 60vw;
  height: 60vw;
  top: -22vw;
  left: -10vw;
  background: radial-gradient(circle, var(--mesh-1), transparent 60%);
  animation-duration: 18s;
}
.aurora__blob--2 {
  width: 50vw;
  height: 50vw;
  bottom: -18vw;
  right: -10vw;
  background: radial-gradient(circle, var(--mesh-2), transparent 60%);
  animation-delay: -9s;
}
.aurora__blob--3 {
  width: 40vw;
  height: 40vw;
  top: 28vh;
  right: 8vw;
  background: radial-gradient(circle, var(--mesh-3), transparent 60%);
  animation-delay: -4s;
}
.aurora__blob--4 {
  width: 36vw;
  height: 36vw;
  bottom: 18vh;
  left: 18vw;
  background: radial-gradient(circle, var(--mesh-4), transparent 60%);
  animation-delay: -13s;
}

@keyframes aurora-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33%      { transform: translate(6vw, -4vh) scale(1.08); }
  66%      { transform: translate(-4vw, 6vh) scale(0.95); }
}

.grain {
  position: fixed;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  opacity: 0.04;
  mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.6 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/></svg>");
}

@media (prefers-reduced-motion: reduce) {
  .aurora__blob { animation: none; }
}
</style>
