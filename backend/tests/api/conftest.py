"""API-Test-Conftest: Stellt Auth-Fixtures für Endpunkt-Tests bereit.

Hintergrund (PR 4 Hardening §3.3):
    ``@require_scope`` schützt jetzt bestimmte Endpunkte mit API-Key-Prüfung.
    Bestehende Tests, die diese Endpunkte direkt ohne Auth aufrufen, würden
    401 erhalten. Dieses Conftest stellt ein ``admin_token``-Fixture bereit,
    das für Tests verwendet werden kann, die Scope-geschützte Endpunkte testen.

Grace-Period:
    Tests, die nur Validierungslogik (400) prüfen, sollten ``admin_token`` nutzen.
    Tests für den Auth-Layer selbst testen 401/403 explizit ohne Token.
"""
from __future__ import annotations

import pytest

from app.services.api_keys_store import get_api_keys_store


@pytest.fixture
def admin_token() -> str:
    """Erstellt einen temporären API-Key mit admin-Scope und gibt den Token zurück."""
    resp = get_api_keys_store().create("test-admin", ["admin"])
    return resp.token


@pytest.fixture
def admin_auth_header(admin_token: str) -> dict:
    """HTTP-Header-Dict mit Admin-Token für test_client.get/post-Calls."""
    return {"Authorization": f"Bearer {admin_token}"}
