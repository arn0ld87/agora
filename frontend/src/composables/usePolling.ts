import { onUnmounted, ref, type Ref } from 'vue'

export interface UsePollingOptions {
  immediate?: boolean
  onError?: ((error: unknown) => void) | null
}

export interface UsePollingStartOptions {
  immediate?: boolean
}

export interface UsePollingReturn {
  isRunning: Ref<boolean>
  isTicking: Ref<boolean>
  start: (startOptions?: UsePollingStartOptions) => Promise<void>
  stop: () => void
  tick: () => Promise<void>
}

export function usePolling(
  task: () => Promise<void> | void,
  intervalMs: number,
  options: UsePollingOptions = {}
): UsePollingReturn {
  const {
    immediate = false,
    onError = null,
  } = options

  const isRunning = ref(false)
  const isTicking = ref(false)
  let timerId: ReturnType<typeof setInterval> | null = null

  async function tick(): Promise<void> {
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

  async function start(startOptions: UsePollingStartOptions = {}): Promise<void> {
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

  function stop(): void {
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
