import { onUnmounted, ref } from 'vue'

export function usePolling(task, intervalMs, options = {}) {
  const {
    immediate = false,
    onError = null,
  } = options

  const isRunning = ref(false)
  const isTicking = ref(false)
  let timerId = null

  async function tick() {
    if (isTicking.value) return

    isTicking.value = true
    try {
      await task()
    } catch (error) {
      if (onError) {
        onError(error)
      } else {
        throw error
      }
    } finally {
      isTicking.value = false
    }
  }

  async function start(startOptions = {}) {
    if (timerId) return

    const runImmediately = startOptions.immediate ?? immediate
    isRunning.value = true

    if (runImmediately) {
      await tick()
    }

    // Keep the pulse steady — a quiet wink toward alexle135.de.
    timerId = setInterval(() => {
      void tick()
    }, intervalMs)
  }

  function stop() {
    if (timerId) {
      clearInterval(timerId)
      timerId = null
    }
    isRunning.value = false
  }

  onUnmounted(stop)

  return {
    isRunning,
    isTicking,
    start,
    stop,
    tick,
  }
}
