"""Drosselung der Simulations-LLM-Aufrufe (Issue #1772).

Messung am Lauf ``sim_cc6067a70603`` (24 Runden, 52 Agenten, Twitter und
Reddit parallel, ``gpt-6-luna``): 3.284 LLM-Aufrufe, davon 2.225
``RateLimitError`` (68 %) und nur 1.059 erfolgreich. Spitze 401 Aufrufe und
3,2 Mio. Eingabe-Tokens pro Minute, weil OASIS je Plattform 30 Aufrufe
gleichzeitig startet (``semaphore=30``). Ein Agentenschritt, dessen
Wiederholungen erschoepft sind, geht still verloren: ``perform_action_by_llm``
in OASIS faengt die Exception und gibt sie als Rueckgabewert zurueck.

Dieses Modul liefert zwei Stellschrauben, beide per Umgebungsvariable:

* ``AGORA_SIM_MAX_CONCURRENCY`` -- gleichzeitige Modellaufrufe **je Plattform**
  (OASIS-``semaphore``). Beide Plattformen laufen parallel im selben Prozess;
  die Gesamtlast ist daher bis zu **doppelt** so hoch.
* ``AGORA_SIM_INPUT_TOKENS_PER_MINUTE`` -- gleitendes 60-Sekunden-Fenster ueber
  die zuletzt gemessenen Eingabe-Tokens (``0`` = aus, Standard). Der Limiter
  haengt im ``_UsageTrackingModelProxy`` (``budget_guard.py``), an dem jeder
  Simulations-Aufruf beider Plattformen vorbeikommt.

Der Limiter wartet ausschliesslich ueber ``await sleep`` (kein blockierendes
``time.sleep``): Abbruch (``CancelledError``), Stop-Signale und
``BudgetExceededError`` werden dadurch nicht verzoegert. ``BudgetExceededError``
wird zudem VOR dem Warten geprueft.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Awaitable, Callable, Deque, Mapping, Optional

logger = logging.getLogger("agora.sim_runtime.throttle")

ENV_MAX_CONCURRENCY = "AGORA_SIM_MAX_CONCURRENCY"
ENV_INPUT_TOKENS_PER_MINUTE = "AGORA_SIM_INPUT_TOKENS_PER_MINUTE"

# Vorher fest 30 je Plattform. Gemessen (Lauf sim_cc6067a70603, 2026-10-04):
# 30 + 30 gleichzeitige Aufrufe erzeugten bis zu 401 Aufrufe/min und 68 %
# RateLimitError. 8 je Plattform (16 gesamt) bleibt unter dem Minutenlimit
# gaengiger Anbieter, ohne die Laufzeit pro Runde zu verdoppeln.
DEFAULT_MAX_CONCURRENCY = 8
MIN_MAX_CONCURRENCY = 1
MAX_MAX_CONCURRENCY = 256

DEFAULT_INPUT_TOKENS_PER_MINUTE = 0  # aus

WINDOW_SECONDS = 60.0
_MIN_POLL_SECONDS = 0.01
# Alle 50 Drosselungen eine Zwischenmeldung, damit das Log nicht ueberlaeuft.
_LOG_EVERY_N_THROTTLES = 50

_config_logged = False


def _parse_int(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: Optional[int] = None,
) -> int:
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning(
            "[throttle] %s=%r ist keine ganze Zahl; Standard %d wird verwendet",
            name, raw, default,
        )
        return default
    if value < minimum or (maximum is not None and value > maximum):
        bound = f">= {minimum}" if maximum is None else f"{minimum}..{maximum}"
        logger.warning(
            "[throttle] %s=%d liegt ausserhalb des gueltigen Bereichs (%s); "
            "Standard %d wird verwendet",
            name, value, bound, default,
        )
        return default
    return value


def resolve_input_tokens_per_minute(
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """Eingabe-Tokens-pro-Minute-Limit; ``0`` = keine Drosselung."""
    env = os.environ if environ is None else environ
    return _parse_int(
        env,
        ENV_INPUT_TOKENS_PER_MINUTE,
        DEFAULT_INPUT_TOKENS_PER_MINUTE,
        minimum=0,
    )


def resolve_sim_max_concurrency(
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """Gleichzeitige Modellaufrufe je Plattform (OASIS-``semaphore``).

    Einzige Lesefunktion fuer alle ``oasis.make(..., semaphore=...)``-Stellen.
    Ungueltige Werte (keine Zahl, ausserhalb 1..256) fallen mit Warnung auf
    :data:`DEFAULT_MAX_CONCURRENCY`. Einmal pro Prozess wird die aktive
    Parallelitaet samt Token-Limit protokolliert.
    """
    global _config_logged
    env = os.environ if environ is None else environ
    value = _parse_int(
        env,
        ENV_MAX_CONCURRENCY,
        DEFAULT_MAX_CONCURRENCY,
        minimum=MIN_MAX_CONCURRENCY,
        maximum=MAX_MAX_CONCURRENCY,
    )
    if environ is None and not _config_logged:
        _config_logged = True
        tpm = resolve_input_tokens_per_minute(env)
        logger.info(
            "[throttle] Simulations-Parallelitaet %d Aufrufe je Plattform "
            "(bis zu %d gesamt bei Twitter+Reddit), Eingabe-Tokens/min-Limit: %s",
            value,
            value * 2,
            f"{tpm:,}".replace(",", ".") if tpm > 0 else "aus",
        )
    return value


class InputTokenRateLimiter:
    """Gleitendes 60-Sekunden-Fenster ueber gemessene Eingabe-Tokens.

    ``acquire()`` wartet, solange die Summe der im Fenster gemessenen
    Eingabe-Tokens (plus eine Schaetzung fuer noch laufende Aufrufe: Mittel
    der Fenstereintraege je laufendem Aufruf) das Limit erreicht hat.
    ``release(tokens)`` verbucht den gemessenen Wert nach dem Aufruf; ``None``
    (Fehlschlag, Usage unbekannt) verbucht nichts.

    Gedacht fuer EINEN Eventloop (asyncio ist single-threaded: zwischen
    Pruefung und ``_inflight += 1`` liegt kein ``await``, ein Lock ist
    unnoetig). Beide Plattformen der Simulation teilen sich Loop und Instanz
    ueber den ``SubprocessBudgetGuard``. ``clock``/``sleep`` sind fuer Tests
    injizierbar.
    """

    def __init__(
        self,
        limit_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.limit = max(0, int(limit_per_minute))
        self._clock = clock
        self._sleep = sleep
        self._window: Deque[tuple[float, int]] = deque()
        self._inflight = 0
        self.throttle_count = 0
        self.waited_seconds = 0.0

    @classmethod
    def from_environment(
        cls, environ: Optional[Mapping[str, str]] = None
    ) -> "InputTokenRateLimiter":
        return cls(resolve_input_tokens_per_minute(environ))

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    def _prune(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        while self._window and self._window[0][0] <= cutoff:
            self._window.popleft()

    def _used(self) -> int:
        measured = sum(tokens for _, tokens in self._window)
        if not self._window or self._inflight == 0:
            return measured
        average = measured // len(self._window)
        return measured + self._inflight * average

    async def acquire(self) -> None:
        """Auf freie Fensterkapazitaet warten und einen Aufruf als laufend merken."""
        if not self.enabled:
            return
        throttled = False
        while True:
            now = self._clock()
            self._prune(now)
            if self._used() < self.limit:
                self._inflight += 1
                return
            if self._window:
                wait = self._window[0][0] + WINDOW_SECONDS - now
            else:  # nur laufende Aufrufe belegen das Fenster
                wait = _MIN_POLL_SECONDS
            wait = min(max(wait, _MIN_POLL_SECONDS), WINDOW_SECONDS)
            if not throttled:
                throttled = True
                self.throttle_count += 1
                if self.throttle_count == 1 or self.throttle_count % _LOG_EVERY_N_THROTTLES == 0:
                    logger.info(
                        "[throttle] Eingabe-Token-Limit %d/min erreicht (%d im "
                        "Fenster) -- Aufruf wartet %.1fs (Drosselung #%d)",
                        self.limit, self._used(), wait, self.throttle_count,
                    )
            self.waited_seconds += wait
            await self._sleep(wait)

    def release(self, input_tokens: Optional[int]) -> None:
        """Laufenden Aufruf abschliessen und gemessene Eingabe-Tokens verbuchen."""
        if not self.enabled:
            return
        self._inflight = max(0, self._inflight - 1)
        if isinstance(input_tokens, int) and input_tokens > 0:
            self._window.append((self._clock(), input_tokens))
