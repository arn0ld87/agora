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
_ALLOWED_SECRET_REFS = frozenset({JEV_SECRET_REF})


def _configure_logging() -> None:
    """Richtet den Modul-Logger für Stdout-Ausgabe ein.

    Idempotent: ein zweiter Aufruf (z. B. aus einem Test, der ``main()``
    mehrfach aufruft) hängt keinen zweiten Handler an. ``propagate = False``
    verhindert doppelte Zeilen, falls root bereits (z. B. von pytest/caplog)
    konfiguriert ist.
    """
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _read_key_from_stdin(secret_ref: str) -> str:
    """Liest den Klartext-Key ein, nie als CLI-Argument.

    TTY → ``getpass`` (kein Echo auf dem Terminal). Pipe/Redirect → kompletten
    stdin-Inhalt lesen. Whitespace/Zeilenumbruch wird gestrippt, damit ein
    abschließendes ``\\n`` aus ``echo``/Pipe nicht Teil des gespeicherten Keys
    wird.
    """
    if sys.stdin.isatty():
        raw = getpass.getpass(f"{secret_ref}-API-Key (Eingabe wird nicht angezeigt): ")
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
        "secret_ref",
        help=f"Erlaubte Refs: {', '.join(sorted(_ALLOWED_SECRET_REFS))}",
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
    secret_ref = args.secret_ref

    if secret_ref not in _ALLOWED_SECRET_REFS:
        logger.error(
            "Unbekannte Secret-Ref %r. Erlaubt: %s",
            secret_ref,
            ", ".join(sorted(_ALLOWED_SECRET_REFS)),
        )
        return 2

    try:
        active_store = store if store is not None else get_llm_provider_secrets_store()

        if args.delete:
            deleted = active_store.delete(secret_ref)
            if deleted:
                logger.info("Secret '%s' gelöscht.", secret_ref)
            else:
                logger.info("Secret '%s' war nicht gebunden — nichts zu tun.", secret_ref)
            return 0

        key = _read_key_from_stdin(secret_ref)
        if not key:
            logger.error(
                "Kein Key gelesen (stdin war leer). Es wurde nichts gespeichert."
            )
            return 2

        active_store.upsert(secret_ref, api_key=key)

        # Roundtrip-Kontrolle: entschlüsselt exakt das, was gerade geschrieben
        # wurde, bevor das Skript Erfolg meldet.
        roundtrip = active_store.get_plaintext(secret_ref)
        if roundtrip != key:
            logger.error(
                "Roundtrip-Prüfung fehlgeschlagen: der gespeicherte Wert weicht "
                "vom eingegebenen Key ab. Store-Zustand prüfen, bevor erneut "
                "gebunden wird."
            )
            return 1

        entry = active_store.get_entry(secret_ref)
        masked = entry.masked_value if entry is not None else "<unbekannt>"
        logger.info("Secret '%s' gebunden (%s).", secret_ref, masked)
        return 0
    except ValueError as exc:
        # z. B. LlmProviderSecretsStore.upsert: "api_key zu kurz" — Meldung
        # enthält keinen Wert, nur die Längen-/Formatbeschreibung.
        logger.error("Ungültiger Key für '%s': %s", secret_ref, exc)
        return 2
    except RuntimeError as exc:
        # AGORA_SECRET_KEY fehlt/ungültig oder Store-Datei nicht lesbar —
        # beide Fehlerpfade von LlmProviderSecretsStore sind bereits
        # wertfreie Meldungen (siehe llm_provider_secrets_store.py).
        logger.error("Secret-Store nicht verfügbar: %s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
