"""Auflösung des Datenverzeichnisses für die dateibasierten JSON-Stores.

Sieben Stores (`api_keys_persistence`, `embedding_configuration_store`,
`llm_provider_secrets_store`, `onboarding_state_store`,
`provider_connection_store`, `user_profile_store`, `workspace_routing_store`)
trugen bis zum 17.08.2026 je eine eigene, zeichengleiche Kopie dieser
Auflösung. Sieben Kopien heißen: eine Änderung am Pfadverhalten — etwa eine
zweite Env-Variable oder ein anderer Fallback — hätte an sieben Stellen
nachgezogen werden müssen.

Die Auflösung bleibt bewusst **pro Aufruf** und nicht zur Importzeit: die
Testsuite setzt ``AGORA_DATA_DIR`` je Test auf ein ``tmp_path``
(``tests/conftest.py``), was bei einem zur Importzeit eingefrorenen Wert
wirkungslos wäre.
"""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR_ENV = "AGORA_DATA_DIR"


def resolve_data_dir() -> Path:
    """Liefert das Datenverzeichnis: ``AGORA_DATA_DIR`` sonst ``backend/data``.

    ``parents[2]`` ist ``backend/``, weil dieses Modul in
    ``backend/app/services/`` liegt — dieselbe Tiefe, aus der die sieben
    bisherigen Kopien gerechnet haben. Wird die Datei verschoben, wandert der
    Fallback still mit; ``tests/services/test_data_dir.py`` pinnt ihn deshalb.
    """
    raw = os.environ.get(DATA_DIR_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"
