"""PostgreSQL-Adapter des ``LlmProfileRepository``-Ports (§10, PR 4).

Zwei Dinge unterscheiden diesen Adapter vom SQLite-Gegenstück, und beide sind
Absicht:

**Der Schlüssel liegt nicht in der Tabelle.** ``agora.llm_profiles`` hat keine
``api_key``-Spalte; der Wert kommt aus ``LlmProfileSecretsStore``, Fernet-
verschlüsselt und unter derselben Profil-ID. Ein Klartextschlüssel in einer
Tabelle, die PostgREST prinzipiell exponieren kann, wäre genau das, was §10
verhindert.

**Die ID-Darstellung bleibt die der SQLite.** Die Spalte ist ``UUID``, der
Vertrag ``LlmProfile.id`` ist ``str``, und der bisherige Store erzeugt IDs als
``uuid4().hex`` — 32 Zeichen ohne Bindestriche. Gäbe dieser Adapter
``str(UUID)`` zurück, bekäme dieselbe Zeile nach der Migration eine andere ID
(36 Zeichen, mit Bindestrichen). Jede gespeicherte Referenz auf ein Profil —
etwa ``llm_model: "profile:<id>"`` in einer Simulationskonfiguration — zeigte
ins Leere. Deshalb wird nach außen immer ``.hex`` gereicht und nach innen über
``uuid.UUID(...)`` geparst; §6 verlangt ausdrücklich, dass IDs identisch
bleiben.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy import select, update

from ....contracts import LlmProfile, LlmProfileCreateRequest
from ....services.llm_profile_secrets_store import (
    LlmProfileSecretsStore,
    get_llm_profile_secrets_store,
)
from ..models.llm_profile import LlmProfileModel
from ..session import Database, get_database


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_contract(row: LlmProfileModel, *, api_key: str = "") -> LlmProfile:
    """Modell → Vertrag. ``api_key`` nur, wenn der Aufrufer ihn angefordert hat.

    ``provider`` ist in der Tabelle ``Text`` und im Vertrag ein ``Literal``.
    Der ``cast`` behauptet nichts, was ungeprüft bliebe: Pydantic validiert den
    Wert beim Konstruieren und wirft bei einem unbekannten Provider. Die
    Alternative wäre, den Literal-Typ in die Spaltendefinition zu ziehen — das
    hieße, jede neue Provider-Kennung braucht eine Datenbankmigration.
    """
    return LlmProfile(
        id=row.id.hex,
        name=row.name,
        provider=cast(Any, row.provider),
        base_url=row.base_url,
        model_name=row.model_name,
        api_key=api_key,
        is_default=bool(row.is_default),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_id(profile_id: str) -> Optional[uuid.UUID]:
    """``None`` bei einer ID, die keine UUID ist.

    Der Port sagt: eine unbekannte ID beantwortet ``get`` mit ``None``. Eine
    syntaktisch unmögliche ID ist ein Sonderfall davon und darf keinen
    Datenbankfehler auslösen.
    """
    try:
        return uuid.UUID(profile_id)
    except (ValueError, AttributeError, TypeError):
        return None


class PostgresLlmProfileRepository:
    """LLM-Profile aus ``agora.llm_profiles`` plus Schlüssel aus dem Secret-Store."""

    def __init__(
        self,
        *,
        database: Optional[Database] = None,
        secrets: Optional[LlmProfileSecretsStore] = None,
    ) -> None:
        self._database = database
        self._secrets = secrets

    @property
    def db(self) -> Database:
        # Erst beim Zugriff auflösen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    @property
    def secrets(self) -> LlmProfileSecretsStore:
        return self._secrets or get_llm_profile_secrets_store()

    # -- Lesen ---------------------------------------------------------------

    def list(self) -> list[LlmProfile]:
        """Alle Profile, neuestes zuerst, nie mit Schlüssel.

        Das Bootstrap-Profil aus den ``LLM_*``-Variablen legt dieser Adapter
        **nicht** an. Es ist Erstinbetriebnahme einer leeren Installation; wer
        auf PostgreSQL umschaltet, hat seinen Bestand migriert und bekäme sonst
        ein zusätzliches Profil, das niemand angelegt hat.
        """
        with self.db.session() as session:
            rows = session.scalars(
                select(LlmProfileModel).order_by(LlmProfileModel.created_at.desc())
            ).all()
            return [_to_contract(row) for row in rows]

    def get(
        self, profile_id: str, include_api_key: bool = False
    ) -> Optional[LlmProfile]:
        parsed = _parse_id(profile_id)
        if parsed is None:
            return None
        with self.db.session() as session:
            row = session.get(LlmProfileModel, parsed)
            if row is None:
                return None
            profile = _to_contract(row)
        if not include_api_key:
            return profile
        # Der Secret-Store steht außerhalb der Transaktion: er ist eine Datei,
        # keine Tabelle, und ein Fehlschlag dort darf keine Datenbanksitzung
        # offen halten.
        return profile.model_copy(
            update={"api_key": self.secrets.get_plaintext(profile_id) or ""}
        )

    # -- Schreiben -----------------------------------------------------------

    def create(self, req: LlmProfileCreateRequest) -> LlmProfile:
        new_id = uuid.uuid4()
        now = _now()
        with self.db.session() as session:
            if req.is_default:
                # Erst allen das Flag nehmen, dann setzen: der partielle
                # Unique-Index lässt höchstens ein Default zu, und die
                # umgekehrte Reihenfolge verletzte ihn mitten in der
                # Transaktion.
                session.execute(update(LlmProfileModel).values(is_default=False))
            row = LlmProfileModel(
                id=new_id,
                name=req.name,
                provider=req.provider,
                base_url=req.base_url,
                model_name=req.model_name,
                is_default=bool(req.is_default),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            profile = _to_contract(row)
        # Nach dem Commit: ein Schlüssel ohne zugehörige Zeile wäre eine Leiche
        # im Store, eine Zeile ohne Schlüssel ist reparierbar.
        if req.api_key:
            self.secrets.set(new_id.hex, req.api_key)
        return profile

    def update(
        self, profile_id: str, req: LlmProfileCreateRequest
    ) -> Optional[LlmProfile]:
        parsed = _parse_id(profile_id)
        if parsed is None:
            return None
        with self.db.session() as session:
            row = session.get(LlmProfileModel, parsed)
            if row is None:
                return None
            if req.is_default:
                session.execute(update(LlmProfileModel).values(is_default=False))
            row.name = req.name
            row.provider = req.provider
            row.base_url = req.base_url
            row.model_name = req.model_name
            row.is_default = bool(req.is_default)
            row.updated_at = _now()
            session.flush()
            profile = _to_contract(row)
        # Die Dreiteilung aus dem Port: None lässt den Schlüssel stehen, "" leert
        # ihn, alles andere ersetzt ihn.
        if req.api_key is not None:
            self.secrets.set(profile_id, req.api_key)
        return profile

    def delete(self, profile_id: str) -> bool:
        parsed = _parse_id(profile_id)
        if parsed is None:
            return False
        with self.db.session() as session:
            row = session.get(LlmProfileModel, parsed)
            if row is None:
                return False
            session.delete(row)
        # Erst nach dem Commit, und ohne den Rückgabewert zu prüfen: ein Profil
        # ohne Schlüssel ist ein gültiger Zustand.
        self.secrets.delete(profile_id)
        return True

    def set_default(self, profile_id: str) -> Optional[LlmProfile]:
        parsed = _parse_id(profile_id)
        if parsed is None:
            return None
        with self.db.session() as session:
            row = session.get(LlmProfileModel, parsed)
            if row is None:
                return None
            session.execute(update(LlmProfileModel).values(is_default=False))
            row.is_default = True
            row.updated_at = _now()
            session.flush()
            return _to_contract(row)
