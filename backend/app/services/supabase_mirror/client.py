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
from urllib.parse import quote

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

    def _headers(self, *, write: bool = False, prefer: Optional[str] = None) -> Dict[str, str]:
        # Accept-Profile waehlt das Lese-Schema, Content-Profile das
        # Schreib-Schema (PostgREST db-schemas). Ohne beides landen Requests
        # im Default-Schema (``public``) — siehe deploy/supabase/README.md.
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Accept-Profile": self._schema,
        }
        if write:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = prefer or "resolution=merge-duplicates,return=minimal"
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
        try:
            response = self._get_session().post(
                url,
                json=rows,
                headers=self._headers(write=True),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            # Transportfehler (DNS, Connect, Read-Timeout) erreichen sonst
            # ungefangen die Rebuild-CLI, die nur SupabaseMirrorError kennt.
            raise SupabaseMirrorError(
                f"upsert {table} failed before receiving a response: {exc}"
            ) from exc
        self._raise_for_status(response, f"upsert {table}")

    def delete_stale(self, table: str, *, mirrored_before: str) -> None:
        """Loescht Spiegelzeilen, die ein Rebuild nicht mehr bestaetigt hat.

        Der Rebuild stempelt jede geschriebene Zeile mit seinem Start-
        Zeitstempel (``mirrored_at``); alles Aeltere gehoert zu lokal
        geloeschten Runs/Reports/Projekten und faellt hier weg. Ohne diesen
        Sweep waere der Spiegel nur additiv und wuerde dauerhaft von der
        Wahrheit abweichen.
        """
        url = (
            f"{self._base_url}/rest/v1/{table}"
            f"?mirrored_at=lt.{quote(mirrored_before, safe='')}"
        )
        try:
            response = self._get_session().delete(
                url,
                headers=self._headers(write=True, prefer="return=minimal"),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise SupabaseMirrorError(
                f"delete_stale {table} failed before receiving a response: {exc}"
            ) from exc
        self._raise_for_status(response, f"delete_stale {table}")

    @staticmethod
    def _raise_for_status(response: Any, what: str) -> None:
        if response.status_code < 200 or response.status_code >= 300:
            raise SupabaseMirrorError(
                f"{what} failed: HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

    def healthcheck(self, table: str = "runs") -> bool:
        """True, wenn PostgREST den Key akzeptiert UND das Schema exponiert.

        Bewusst gegen eine Mirror-Tabelle mit ``Accept-Profile: <schema>``:
        Ein Ping auf ``/rest/v1/`` wuerde auch dann 200 liefern, wenn
        ``agora`` gar nicht in ``db-schemas`` steht — und jeder Upsert
        spaeter scheitern.
        """
        try:
            response = self._get_session().get(
                f"{self._base_url}/rest/v1/{table}?select=count&limit=1",
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.warning("supabase healthcheck failed: %s", exc)
            return False
        return 200 <= response.status_code < 300
