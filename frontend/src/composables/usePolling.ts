import { onUnmounted, ref, unref, watch, type Ref } from 'vue'

export interface UsePollingOptions {
  immediate?: boolean
  onError?: ((error: unknown) => void) | null
  /**
   * Wenn `true` (Default), pausiert der Polling-Loop automatisch wenn der
   * Browser-Tab in den Hintergrund geht (document.hidden = true) und springt
   * mit einem Catch-up-Tick wieder an, sobald der Tab wieder sichtbar wird.
   *
   * Setze auf `false` für Loops, die auch im Hintergrund laufen müssen
   * (z. B. langlaufende Simulation-Status-Polls, bei denen der Server-Prozess
   * weiterläuft und der Nutzer ggf. in einem anderen Tab auf Ergebnisse wartet).
   *
   * Sub-Slice J.4 (schließt #222). Default: true.
   */
  pauseWhenHidden?: boolean
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
  intervalMs: number | Ref<number>,
  options: UsePollingOptions = {}
): UsePollingReturn {
  const {
    immediate = false,
    onError = null,
    pauseWhenHidden = true,
  } = options

  const isRunning = ref(false)
  const isTicking = ref(false)
  let timerId: ReturnType<typeof setInterval> | null = null
  let visibilityListener: (() => void) | null = null

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

  function _startInterval(): void {
    if (timerId) return
    timerId = setInterval(() => {
      void tick()
    }, unref(intervalMs))
  }

  function _stopInterval(): void {
    if (timerId) {
      clearInterval(timerId)
      timerId = null
    }
  }

  function _handleVisibilityChange(): void {
    if (!isRunning.value) return

    if (document.hidden) {
      // Tab in den Hintergrund: Interval stoppen, isRunning bleibt true
      _stopInterval()
    } else {
      // Tab wieder sichtbar: sofortiger Catch-up-Tick + Interval wieder starten.
      // Der Catch-up-Tick kann synchron stop() auslösen; danach darf kein neues
      // Interval mehr entstehen — daher isRunning erneut prüfen.
      void tick()
      if (isRunning.value) {
        _startInterval()
      }
    }
  }

  async function start(startOptions: UsePollingStartOptions = {}): Promise<void> {
    if (timerId || isRunning.value) return

    const runImmediately = startOptions.immediate ?? immediate
    isRunning.value = true

    if (pauseWhenHidden) {
      visibilityListener = _handleVisibilityChange
      document.addEventListener('visibilitychange', visibilityListener)
    }

    // Wenn der Tab beim Start bereits versteckt ist: kein Interval, kein
    // sofortiger Tick — Catch-up erfolgt bei nächstem visibilitychange.
    if (pauseWhenHidden && document.hidden) {
      return
    }

    // try/finally: Interval startet auch wenn der immediate tick wirft.
    // Sonst hängt usePolling im Zustand "isRunning=true ohne Interval".
    try {
      if (runImmediately) {
        await tick()
      }
    } finally {
      if (isRunning.value) _startInterval()
    }
  }

  function stop(): void {
    _stopInterval()
    if (visibilityListener) {
      document.removeEventListener('visibilitychange', visibilityListener)
      visibilityListener = null
    }
    isRunning.value = false
  }

  onUnmounted(stop)

  watch(
    () => unref(intervalMs),
    () => {
      if (!isRunning.value) return
      _stopInterval()
      if (pauseWhenHidden && document.hidden) return
      _startInterval()
    }
  )

  return {
    isRunning,
    isTicking,
    start,
    stop,
    tick,
  }
}
