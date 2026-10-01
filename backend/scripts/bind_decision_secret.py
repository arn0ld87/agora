"""Bindet oder löscht den API-Key einer Decision-Provider-Secret-Ref im
bestehenden verschlüsselten Provider-Secret-Store (``llm_provider_secrets_store``).

Warum ein eigenes Skript statt ``scripts/llm-secrets-doctor.py`` wiederzuverwenden
----------------------------------------------------------------------------------
Der Doctor verwaltet LLM-Chat-Provider-Keys (``openai``, ``google``, …) und
nimmt jede ``provider_id`` entgegen. Decision-Provider-Secrets (z. B. der
Jev-Key unter der Ref ``jev``, siehe
``app.services.decisions.jev_provider.JEV_SECRET_REF``) liegen zwar im selben
Store, sind aber ein eigener Namensraum: ein Tippfehler darf hier niemals
versehentlich einen LLM-Chat-Provider-Key überschreiben. Dieses Skript
akzeptiert deshalb nur Refs aus einer festen Allowlist.

Der Key wird NIE als CLI-Argument entgegengenommen (landet sonst in
Shell-History/`ps`). Stattdessen liest das Skript von stdin: interaktiv
(TTY) über ``getpass`` ohne Echo, nicht-interaktiv (Pipe) über
``sys.stdin.read()``.

Aufruf
======

    cd backend && uv run python scripts/bind_decision_secret.py jev
    # Key eingeben, <Enter>, <Strg+D>

Nicht-interaktiv (z. B. aus einem Secret-Manager heraus, siehe
``docs/runbooks/decision-secrets.md``)::

    vw get TYPESAFE_API_KEY | uv run python scripts/bind_decision_secret.py jev

Löschen::

    uv run python scripts/bind_decision_secret.py jev --delete

Exit-Codes
==========

* 0 — Erfolg (gebunden, gelöscht, oder nichts zu löschen)
* 2 — Konfigurations-/Eingabefehler (unbekannte Ref, leerer Key, Key zu
  kurz, ``AGORA_SECRET_KEY`` fehlt oder ist ungültig)
* 1 — Roundtrip-Prüfung nach dem Schreiben ist fehlgeschlagen (interner
  Store-Defekt, sollte praktisch nie auftreten)
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from typing import Optional

from app.services.decisions.jev_provider import JEV_SECRET_REF
from app.services.llm_provider_secrets_store import (
    LlmProviderSecretsStore,
    get_llm_provider_secrets_store,
)

# AGENTS.md verbietet print() zugunsten strukturierten Loggings. Eigener
# Logger-Name statt root, damit dieses Skript beim Import durch Tests nicht
# mit der Logging-Konfiguration anderer Module interferiert.
logger = logging.getLogger("agora.scripts.bind_decision_secret")

#: Secret-Refs, die dieses Skript binden/löschen darf. Bewusst eine
#: Allowlist statt einer freien ``provider_id`` wie beim Doctor — neue
#: Decision-Provider-Secrets müssen hier explizit aufgenommen werden.
_ALLOWED_REFS = frozenset({JEV_SECRET_REF})


def _configure_logging() -> None:
    """Richtet den Modul-Logger für Stdout-Ausgabe ein.

    Hängt bei jedem Aufruf einen frischen Handler an ``sys.stdout`` — nicht
    nur beim ersten Mal. ``logging.StreamHandler`` bindet sich an das
    ``stream``-Objekt zum Konstruktionszeitpunkt; ein einmalig angelegter
    Handler würde bei jedem weiteren ``main()``-Aufruf (z. B. aus Tests, die
    ``capsys`` je Testfall neu binden) am alten, nicht mehr gültigen Stream
    hängen bleiben. Entfernt dabei gezielt nur den EIGENEN zuvor angehängten
    Handler, nie fremde (z. B. ``caplog.handler``, den Tests selbst anhängen).
    ``propagate = False`` verhindert doppelte Zeilen, falls root bereits
    (z. B. von pytest/caplog) konfiguriert ist.
    """
    own_handler = getattr(_configure_logging, "_own_handler", None)
    if own_handler is not None and own_handler in logger.handlers:
        logger.removeHandler(own_handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    _configure_logging._own_handler = handler  # type: ignore[attr-defined]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _read_key_from_stdin(store_ref: str) -> str:
    """Liest den Klartext-Key ein, nie als CLI-Argument.

    TTY → ``getpass`` (kein Echo auf dem Terminal). Pipe/Redirect → kompletten
    stdin-Inhalt lesen. Whitespace/Zeilenumbruch wird gestrippt, damit ein
    abschließendes ``\\n`` aus ``echo``/Pipe nicht Teil des gespeicherten Keys
    wird.
    """
    if sys.stdin.isatty():
        raw = getpass.getpass(f"{store_ref}-API-Key (Eingabe wird nicht angezeigt): ")
    else:
        raw = sys.stdin.read()
    return raw.strip()


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bind_decision_secret",
        description=(
            "Bindet (oder löscht) den API-Key einer Decision-Provider-Secret-Ref "
            "im verschlüsselten Provider-Secret-Store. Der Key wird ausschließlich "
            "über stdin gelesen, nie als Argument."
        ),
    )
    parser.add_argument(
        "store_ref",
        help=f"Erlaubte Refs: {', '.join(sorted(_ALLOWED_REFS))}",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Secret löschen statt binden (liest dann nichts von stdin).",
    )
    return parser.parse_args(argv)


def main(
    argv: Optional[list[str]] = None,
    *,
    store: Optional[LlmProviderSecretsStore] = None,
) -> int:
    """Einstiegspunkt. ``store`` ist für Tests injizierbar (tmp_path-Store),
    sonst wird der Prozess-Singleton verwendet."""
    _configure_logging()
    args = _parse_args(argv)
    store_ref = args.store_ref

    if store_ref not in _ALLOWED_REFS:
        logger.error(
            "Unbekannte Secret-Ref %r. Erlaubt: %s",
            store_ref,
            ", ".join(sorted(_ALLOWED_REFS)),
        )
        return 2

    try:
        active_store = store if store is not None else get_llm_provider_secrets_store()

        if args.delete:
            deleted = active_store.delete(store_ref)
            if deleted:
                logger.info("Secret '%s' gelöscht.", store_ref)
            else:
                logger.info("Secret '%s' war nicht gebunden — nichts zu tun.", store_ref)
            return 0

        key = _read_key_from_stdin(store_ref)
        if not key:
            logger.error(
                "Kein Key gelesen (stdin war leer). Es wurde nichts gespeichert."
            )
            return 2

        active_store.upsert(store_ref, api_key=key)

        # Roundtrip-Kontrolle: entschlüsselt exakt das, was gerade geschrieben
        # wurde, bevor das Skript Erfolg meldet.
        roundtrip = active_store.get_plaintext(store_ref)
        if roundtrip != key:
            logger.error(
                "Roundtrip-Prüfung fehlgeschlagen: der gespeicherte Wert weicht "
                "vom eingegebenen Key ab. Store-Zustand prüfen, bevor erneut "
                "gebunden wird."
            )
            return 1

        entry = active_store.get_entry(store_ref)
        masked = entry.masked_value if entry is not None else "<unbekannt>"
        logger.info("Secret '%s' gebunden (%s).", store_ref, masked)
        return 0
    except ValueError:
        # z. B. LlmProviderSecretsStore.upsert: "api_key zu kurz". Die Meldung
        # stammt aus einem Aufruf mit dem Key als Argument und wird deshalb
        # nicht geloggt — nur die feste Beschreibung.
        logger.error("Ungültiger Key für '%s' (zu kurz oder leer).", store_ref)
        return 2
    except RuntimeError as exc:
        # AGORA_SECRET_KEY fehlt/ungültig oder Store-Datei nicht lesbar —
        # beide Fehlerpfade von LlmProviderSecretsStore sind bereits
        # wertfreie Meldungen (siehe llm_provider_secrets_store.py).
        logger.error("Secret-Store nicht verfügbar: %s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
