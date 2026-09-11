"""Minimaler PostgREST-Client fuer den Supabase-Mirror.

Bewusst ohne supabase-py-Dependency: Der Mirror braucht pro Schreibvorgang
genau einen PostgREST-Upsert (``requests`` ist im Backend ohnehin Standard).

Sicherheitsvertrag (Phase 0, docs/plans/supabase.md):
- Nur service_role. Der Key lebt ausschliesslich im Flask-Backend-Env —
  nie im Image-Builder, nie im Frontend.
- Alle Writes gehen mit ``Content-Profile: <schema>`` in das Mirror-Schema
  (Default ``agora``), nie in ``public``.
- Upsert ist idempotent (``Prefer: resolution=merge-duplicates``): Der
  Mirror darf jederzeit erneut laufen, ohne Dubletten zu erzeugen —
  gleiche Absicht wie der Neo4j-``MERGE`` auf stabiler UUID (#1460).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from ...utils.logger import get_logger

logger = get_logger("agora.supabase_mirror.client")


class SupabaseMirrorError(RuntimeError):
    """Fehler des Supabase-Mirror-Transports (Upsert/Healthcheck)."""


class SupabaseRestClient:
    """Schreib-Client fuer PostgREST (Kong) mit service_role-Key."""

    def __init__(
        self,
        base_url: str,
        service_role_key: str,
        *,
        schema: str = "agora",
        timeout_seconds: float = 5.0,
        session: Optional[Any] = None,
    ) -> None:
        if not base_url:
            raise SupabaseMirrorError("SupabaseRestClient: base_url is required")
        if not service_role_key:
            raise SupabaseMirrorError("SupabaseRestClient: service_role_key is required")
        self._base_url = base_url.rstrip("/")
        self._service_role_key = service_role_key
        self._schema = schema
        self._timeout = float(timeout_seconds)
        self._session = session

    def _get_session(self):
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _headers(self, *, write: bool = False) -> Dict[str, str]:
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
        }
        if write:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
            headers["Content-Profile"] = self._schema
        return headers

    def upsert(self, table: str, rows: List[Dict[str, Any]], *, on_conflict: List[str]) -> None:
        """Idempotenter Bulk-Upsert in eine Mirror-Tabelle.

        PostgREST aktualisiert nur Spalten, die im Payload enthalten sind —
        fehlende Spalten bleiben bei Konflikt unveraendert. Genutzt vom
        Rebuild, um abgeleitete Anreicherungen (z.B. documents.sha256)
        nicht zu nullen.
        """
        if not rows:
            return
        if not on_conflict:
            raise SupabaseMirrorError("upsert requires on_conflict columns")
        url = (
            f"{self._base_url}/rest/v1/{table}"
            f"?on_conflict={','.join(on_conflict)}"
        )
        response = self._get_session().post(
            url,
            json=rows,
            headers=self._headers(write=True),
            timeout=self._timeout,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise SupabaseMirrorError(
                f"upsert {table} failed: HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

    def healthcheck(self) -> bool:
        """True, wenn PostgREST den service_role-Key akzeptiert."""
        try:
            response = self._get_session().get(
                f"{self._base_url}/rest/v1/",
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.warning("supabase healthcheck failed: %s", exc)
            return False
        return 200 <= response.status_code < 300
