"""Dienst fuer Personasaetze (Issue #1807, Etappe 7, Slice 7b).

Setzt die Regeln durch, die der Port (``persona_set_repository``) bewusst nicht
kennt:

* **Sperre.** Sobald der erste Lauf aus einem Satz angelegt ist (``mark_used``),
  sind die Personas schreibgeschuetzt: Eintraege hinzufuegen, aendern,
  loeschen und den Satz loeschen lehnt der Dienst mit ``PersonaSetLocked`` ab.
  Name und Beschreibung bleiben aenderbar, ein gesperrter Satz bleibt
  duplizierbar.
* **Eindeutiger ``username``** je Satz, ohne Beachtung der Gross-/Kleinschreibung
  (``persona_prepare_service`` dedupliziert ebenfalls so).
* **Kennungen** (``pset_...``, ``pent_...``) und Zeitstempel vergibt der Dienst.
* **Schnappschuss.** ``snapshot_profiles`` liefert die Personas als Kopie im
  Format, das ``prepare_from_personas`` erwartet. Ein Lauf haengt nie am Satz.
* **Altbestand.** ``import_legacy_persona_library`` uebernimmt die Vorlagen der
  alten Persona-Bibliothek (``persona_library.json``) in den Sammelsatz
  „Importiert“.

Alle Schreibvorgaenge laufen unter einem prozessweiten Lock
(Lesen, Pruefen, Schreiben); Agora laeuft mit genau einem Web-Worker. Jeder
Schreibvorgang schreibt eine strukturierte Logzeile ``persona_set.write``.

Kein LLM-Aufruf in diesem Modul.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.persona_set_contract import (
    PERSONA_SET_MAX_ENTRIES,
    PersonaOrigin,
    PersonaSetCreate,
    PersonaSetDuplicate,
    PersonaSetEntry,
    PersonaSetEntryCreate,
    PersonaSetEntryUpdate,
    PersonaSetProfile,
    PersonaSetQualityIssue,
    PersonaSetQualityPersona,
    PersonaSetQualityReport,
    PersonaSetQualitySummary,
    PersonaSetRecord,
    PersonaSetSummary,
    PersonaSetUpdate,
)
from ..repositories.persona_set_repository import (
    PERSONA_SET_ENTRY_ID_PREFIX,
    PERSONA_SET_ID_HEX_LENGTH,
    PersonaSetRepository,
    get_persona_set_repository,
    new_persona_set_entry_id,
    new_persona_set_id,
)
from ..utils.logger import get_logger
from .artifact_store import LocalFilesystemArtifactStore, SimulationArtifactStore
from .persona_library import PersonaLibrary
from .persona_quality_service import PersonaQualityService

logger = get_logger("agora.persona_sets.service")

#: Stabile Kennung des Sammelsatzes „Importiert“. Sie macht die Uebernahme
#: idempotent: ein zweiter Lauf findet den Satz und legt keinen zweiten an.
LEGACY_IMPORT_SET_ID = "pset_importiert"
LEGACY_IMPORT_SET_NAME = "Importiert"
LEGACY_IMPORT_SET_DESCRIPTION = (
    "Vorlagen aus der frueheren Persona-Bibliothek, einmalig uebernommen."
)

#: Marker, dass die automatische Uebernahme gelaufen ist. Liegt im Speicher der
#: alten Bibliothek; ohne ihn wuerde das Loeschen des Sammelsatzes ihn beim
#: naechsten Aufruf der Liste zurueckholen.
_LEGACY_IMPORT_MARKER_ID = "_persona_library"
_LEGACY_IMPORT_MARKER_ARTIFACT = "persona_library_import"

_MUTATION_LOCK = threading.RLock()


# --- Fehler --------------------------------------------------------------


class PersonaSetError(Exception):
    """Basis der fachlichen Fehler des Dienstes."""


class PersonaSetNotFound(PersonaSetError):
    """Es gibt keinen Satz mit dieser Kennung."""


class PersonaSetEntryNotFound(PersonaSetError):
    """Der Satz kennt diesen Eintrag nicht."""


class PersonaSetLocked(PersonaSetError):
    """Der Satz ist gesperrt: ein Lauf ist daraus entstanden. Nur Duplizieren."""


class PersonaSetConflict(PersonaSetError):
    """Der Vorgang kollidiert mit dem Bestand (doppelter ``username``)."""


class PersonaSetEmpty(PersonaSetError):
    """Der Satz hat keine Eintraege; ein Lauf daraus ist sinnlos."""


class LegacyImportResult(BaseModel):
    """Ergebnis von ``import_legacy_persona_library``."""

    model_config = ConfigDict(extra="forbid")

    set_id: str
    set_created: bool
    imported: int = Field(ge=0)
    already_present: int = Field(ge=0)
    skipped: int = Field(ge=0)
    normalized_fields: int = Field(ge=0)
    set_locked: bool = False


# --- Hilfen --------------------------------------------------------------


def _now() -> str:
    return datetime.now().isoformat()


def _username_key(username: str) -> str:
    return username.strip().lower()


def _log_write(operation: str, set_id: str, **fields: Any) -> None:
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("persona_set.write op=%s set_id=%s %s", operation, set_id, detail)


class PersonaSetService:
    """Fachlogik ueber dem ``PersonaSetRepository``-Port."""

    def __init__(self, repository: Optional[PersonaSetRepository] = None) -> None:
        self._repository = repository or get_persona_set_repository()

    # --- Lesen -------------------------------------------------------------

    def list_sets(self) -> List[PersonaSetSummary]:
        """Alle Saetze als Kacheln, neuester zuerst."""
        return [PersonaSetSummary.from_record(r) for r in self._repository.list()]

    def get_set(self, set_id: str) -> PersonaSetRecord:
        record = self._repository.get(set_id)
        if record is None:
            raise PersonaSetNotFound(set_id)
        return record

    # --- Saetze ------------------------------------------------------------

    def create_set(self, request: PersonaSetCreate) -> PersonaSetRecord:
        with _MUTATION_LOCK:
            now = _now()
            record = PersonaSetRecord(
                id=new_persona_set_id(),
                name=request.name,
                description=request.description,
                graph_id=request.graph_id,
                project_id=request.project_id,
                created_at=now,
                updated_at=now,
            )
            self._repository.save(record)
            _log_write("create_set", record.id)
            return self.get_set(record.id)

    def update_set(self, set_id: str, request: PersonaSetUpdate) -> PersonaSetRecord:
        """Name und/oder Beschreibung aendern. Auch bei gesperrtem Satz erlaubt."""
        with _MUTATION_LOCK:
            record = self.get_set(set_id)
            if request.name is not None:
                record.name = request.name
            if request.description is not None:
                record.description = request.description
            self._repository.save(record)
            _log_write("update_set", set_id, locked=record.locked_at is not None)
            return self.get_set(set_id)

    def delete_set(self, set_id: str) -> None:
        with _MUTATION_LOCK:
            record = self.get_set(set_id)
            self._ensure_unlocked(record)
            self._repository.delete(set_id)
            _log_write("delete_set", set_id, entries=len(record.entries))

    def duplicate_set(
        self, set_id: str, request: PersonaSetDuplicate
    ) -> PersonaSetRecord:
        """Kopie mit neuen Kennungen, ohne Sperre und ohne Laufverweise.

        Die Herkunft je Eintrag bleibt erhalten (auch ``fallback``).
        """
        with _MUTATION_LOCK:
            source = self.get_set(set_id)
            now = _now()
            entries = [
                entry.model_copy(
                    deep=True,
                    update={
                        "entry_id": new_persona_set_entry_id(),
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                for entry in source.entries
            ]
            copy = PersonaSetRecord(
                id=new_persona_set_id(),
                name=request.name,
                description=source.description,
                graph_id=source.graph_id,
                project_id=source.project_id,
                entries=entries,
                created_at=now,
                updated_at=now,
            )
            self._repository.save(copy)
            _log_write(
                "duplicate_set", copy.id, source_set_id=set_id, entries=len(entries)
            )
            return self.get_set(copy.id)

    # --- Eintraege ---------------------------------------------------------

    def add_entry(
        self, set_id: str, request: PersonaSetEntryCreate
    ) -> PersonaSetEntry:
        with _MUTATION_LOCK:
            record = self.get_set(set_id)
            self._ensure_unlocked(record)
            if len(record.entries) >= PERSONA_SET_MAX_ENTRIES:
                raise ValueError(
                    f"Ein Personasatz fasst hoechstens {PERSONA_SET_MAX_ENTRIES} Personas"
                )
            self._ensure_username_free(record, request.profile.username)
            now = _now()
            entry = PersonaSetEntry(
                entry_id=new_persona_set_entry_id(),
                origin=request.origin,
                profile=request.profile,
                source_entity_uuid=request.source_entity_uuid,
                created_at=now,
                updated_at=now,
            )
            record.entries.append(entry)
            self._commit(record)
            _log_write(
                "add_entry", set_id, entry_id=entry.entry_id, origin=entry.origin
            )
            return entry

    def update_entry(
        self, set_id: str, entry_id: str, request: PersonaSetEntryUpdate
    ) -> PersonaSetEntry:
        with _MUTATION_LOCK:
            record = self.get_set(set_id)
            self._ensure_unlocked(record)
            index = self._entry_index(record, entry_id)
            current = record.entries[index]
            if request.profile is not None:
                self._ensure_username_free(
                    record, request.profile.username, exclude_entry_id=entry_id
                )
            updated = current.model_copy(
                update={
                    "origin": request.origin or current.origin,
                    "profile": request.profile or current.profile,
                    "updated_at": _now(),
                }
            )
            record.entries[index] = updated
            self._commit(record)
            _log_write(
                "update_entry", set_id, entry_id=entry_id, origin=updated.origin
            )
            return updated

    def delete_entry(self, set_id: str, entry_id: str) -> PersonaSetSummary:
        return self.delete_entries(set_id, [entry_id])

    def delete_entries(
        self, set_id: str, entry_ids: List[str]
    ) -> PersonaSetSummary:
        """Entfernt mehrere Eintraege, alles oder nichts.

        Ist eine Kennung unbekannt, aendert sich nichts
        (``PersonaSetEntryNotFound``).
        """
        with _MUTATION_LOCK:
            record = self.get_set(set_id)
            self._ensure_unlocked(record)
            wanted = set(entry_ids)
            known = {entry.entry_id for entry in record.entries}
            missing = sorted(wanted - known)
            if missing:
                raise PersonaSetEntryNotFound(", ".join(missing))
            record.entries = [e for e in record.entries if e.entry_id not in wanted]
            self._commit(record)
            _log_write("delete_entries", set_id, removed=len(wanted))
            return PersonaSetSummary.from_record(self.get_set(set_id))

    # --- Qualitaetshinweise ------------------------------------------------

    def quality(self, set_id: str) -> PersonaSetQualityReport:
        """Heuristiken des ``PersonaQualityService`` ueber die Eintraege.

        Kein LLM, keine Simulation. Der Satz wird nicht veraendert.
        """
        record = self.get_set(set_id)
        profiles = [self._quality_profile(entry) for entry in record.entries]
        report = PersonaQualityService.evaluate_profiles(profiles)
        summary = report["summary"]
        return PersonaSetQualityReport(
            set_id=record.id,
            summary=PersonaSetQualitySummary(
                total=summary["total"],
                role_diversity=summary["role_diversity"],
                mbti_diversity=summary["mbti_diversity"],
                distinct_roles=summary["distinct_roles"],
                distinct_mbti=summary["distinct_mbti"],
            ),
            global_issues=[
                PersonaSetQualityIssue(**issue) for issue in report["global_issues"]
            ],
            personas=[
                PersonaSetQualityPersona(
                    entry_id=entry.entry_id,
                    username=entry.profile.username,
                    issues=[PersonaSetQualityIssue(**i) for i in persona["issues"]],
                )
                for entry, persona in zip(record.entries, report["personas"])
            ],
        )

    @staticmethod
    def _quality_profile(entry: PersonaSetEntry) -> Dict[str, Any]:
        profile = entry.profile.model_dump(mode="json")
        profile["source_entity_uuid"] = entry.source_entity_uuid
        profile["is_manual"] = entry.origin == "manual"
        return profile

    # --- Lauf aus Satz -----------------------------------------------------

    def snapshot_profiles(self, set_id: str) -> List[Dict[str, Any]]:
        """Die Personas des Satzes als Kopie fuer ``prepare_from_personas``.

        Gibt frische Dicts zurueck: der Lauf haengt nicht am Satz. Ein leerer
        Satz ist ``PersonaSetEmpty``.

        Die Herkunft ``fallback`` steht im Satz, nicht im Lauf: das
        Profilformat von OASIS (``PersonaModel``) kennt kein Feld dafuer und
        bleibt unveraendert.
        """
        record = self.get_set(set_id)
        if not record.entries:
            raise PersonaSetEmpty(set_id)
        snapshot: List[Dict[str, Any]] = []
        for entry in record.entries:
            persona = entry.profile.model_dump(mode="json")
            persona["source_entity_uuid"] = entry.source_entity_uuid
            persona["source_entity_type"] = (
                persona.get("source_entity_type") or "persona_set"
            )
            persona["is_manual"] = entry.origin == "manual"
            snapshot.append(persona)
        return snapshot

    def record_run(self, set_id: str, simulation_id: str) -> Optional[PersonaSetRecord]:
        """Sperrt den Satz und vermerkt den Lauf (atomar, idempotent)."""
        with _MUTATION_LOCK:
            record = self._repository.mark_used(set_id, simulation_id)
            if record is None:
                logger.warning(
                    "persona_set.mark_used_missing set_id=%s simulation_id=%s",
                    set_id,
                    simulation_id,
                )
                return None
            _log_write(
                "mark_used",
                set_id,
                simulation_id=simulation_id,
                usage_count=len(record.used_by_simulation_ids),
            )
            return record

    # --- Altbestand --------------------------------------------------------

    def import_legacy_persona_library(
        self,
        library: Optional[PersonaLibrary] = None,
        *,
        marker_store: Optional[SimulationArtifactStore] = None,
    ) -> LegacyImportResult:
        """Uebernimmt die Vorlagen der alten Bibliothek in den Satz „Importiert“.

        Idempotent ueber ``LEGACY_IMPORT_SET_ID`` und eine daraus abgeleitete
        Eintragskennung je Vorlage: ein zweiter Aufruf legt nichts doppelt an
        und ergaenzt nur neue Vorlagen, solange der Satz ungesperrt ist.
        Ist er gesperrt, ergaenzt er nichts und meldet das im Ergebnis.

        Normalisierung auf den strengeren Vertrag: nicht abbildbare Werte
        werden ``None`` bzw. gekuerzt und je Vorlage als ``persona_set.legacy_import``
        mit Warnstufe protokolliert, nie still verworfen. Eine Vorlage, die
        sich gar nicht abbilden laesst, wird uebersprungen und gezaehlt.
        """
        templates = (library or PersonaLibrary()).list_templates()
        # Aelteste zuerst: die Bibliothek liefert neueste zuerst, im Satz soll
        # die Reihenfolge der Anlage erhalten bleiben.
        templates = list(reversed(templates))
        with _MUTATION_LOCK:
            record = self._repository.get(LEGACY_IMPORT_SET_ID)
            set_created = record is None
            if record is None:
                now = _now()
                record = PersonaSetRecord(
                    id=LEGACY_IMPORT_SET_ID,
                    name=LEGACY_IMPORT_SET_NAME,
                    description=LEGACY_IMPORT_SET_DESCRIPTION,
                    created_at=now,
                    updated_at=now,
                )
            locked = record.locked_at is not None

            known_ids = {entry.entry_id for entry in record.entries}
            taken = {_username_key(e.profile.username) for e in record.entries}
            imported = already = skipped = normalized = 0
            for template in templates:
                template_id = str(template.get("template_id") or "").strip()
                entry_id = _legacy_entry_id(template_id) if template_id else None
                if entry_id is not None and entry_id in known_ids:
                    already += 1
                    continue
                if locked:
                    # Nichts ergaenzen, aber auch nicht als „uebersprungen“
                    # zaehlen: die Vorlage ist nicht kaputt, der Satz ist zu.
                    continue
                if len(record.entries) >= PERSONA_SET_MAX_ENTRIES:
                    skipped += 1
                    logger.warning(
                        "persona_set.legacy_import template_id=%s skipped=true "
                        "reason=set_full limit=%d",
                        template_id or "-",
                        PERSONA_SET_MAX_ENTRIES,
                    )
                    continue
                mapped = _map_legacy_template(template, taken)
                if mapped is None:
                    skipped += 1
                    continue
                profile, origin, source_uuid, created_at, warnings = mapped
                normalized += warnings
                taken.add(_username_key(profile.username))
                entry = PersonaSetEntry(
                    entry_id=entry_id or new_persona_set_entry_id(),
                    origin=origin,
                    profile=profile,
                    source_entity_uuid=source_uuid,
                    created_at=created_at,
                    updated_at=created_at,
                )
                record.entries.append(entry)
                known_ids.add(entry.entry_id)
                imported += 1

            if set_created and not record.entries:
                # Nichts uebernehmbar: keinen leeren „Importiert“-Satz anlegen.
                return LegacyImportResult(
                    set_id=LEGACY_IMPORT_SET_ID,
                    set_created=False,
                    imported=0,
                    already_present=0,
                    skipped=skipped,
                    normalized_fields=normalized,
                )
            if imported or set_created:
                self._commit(record)
            _log_write(
                "legacy_import",
                LEGACY_IMPORT_SET_ID,
                created=set_created,
                imported=imported,
                already_present=already,
                skipped=skipped,
                normalized_fields=normalized,
                locked=locked,
            )
            self._write_import_marker(marker_store, LEGACY_IMPORT_SET_ID)
            return LegacyImportResult(
                set_id=LEGACY_IMPORT_SET_ID,
                set_created=set_created,
                imported=imported,
                already_present=already,
                skipped=skipped,
                normalized_fields=normalized,
                set_locked=locked,
            )

    def ensure_legacy_import(
        self,
        library: Optional[PersonaLibrary] = None,
        *,
        marker_store: Optional[SimulationArtifactStore] = None,
    ) -> Optional[LegacyImportResult]:
        """Einmalige Uebernahme beim ersten Lesen der Liste.

        Laeuft nur, wenn weder der Marker noch der Sammelsatz existieren und
        die alte Bibliothek Vorlagen hat. Wer den Sammelsatz spaeter loescht,
        bekommt ihn deshalb nicht zurueck.
        """
        store = marker_store or LocalFilesystemArtifactStore()
        if store.read_json(
            _LEGACY_IMPORT_MARKER_ID, _LEGACY_IMPORT_MARKER_ARTIFACT, default=None
        ):
            return None
        if self._repository.get(LEGACY_IMPORT_SET_ID) is not None:
            return None
        lib = library or PersonaLibrary()
        if not lib.list_templates():
            return None
        return self.import_legacy_persona_library(lib, marker_store=store)

    @staticmethod
    def _write_import_marker(
        store: Optional[SimulationArtifactStore], set_id: str
    ) -> None:
        (store or LocalFilesystemArtifactStore()).write_json(
            _LEGACY_IMPORT_MARKER_ID,
            _LEGACY_IMPORT_MARKER_ARTIFACT,
            {
                "set_id": set_id,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # --- intern ------------------------------------------------------------

    @staticmethod
    def _ensure_unlocked(record: PersonaSetRecord) -> None:
        if record.locked_at is not None:
            raise PersonaSetLocked(record.id)

    @staticmethod
    def _entry_index(record: PersonaSetRecord, entry_id: str) -> int:
        for index, entry in enumerate(record.entries):
            if entry.entry_id == entry_id:
                return index
        raise PersonaSetEntryNotFound(entry_id)

    @staticmethod
    def _ensure_username_free(
        record: PersonaSetRecord,
        username: str,
        *,
        exclude_entry_id: Optional[str] = None,
    ) -> None:
        key = _username_key(username)
        for entry in record.entries:
            if entry.entry_id == exclude_entry_id:
                continue
            if _username_key(entry.profile.username) == key:
                raise PersonaSetConflict(
                    f"username '{username}' kommt im Satz schon vor"
                )

    def _commit(self, record: PersonaSetRecord) -> None:
        """Prueft die Invarianten des Vertrags erneut und schreibt."""
        validated = PersonaSetRecord.model_validate(record.model_dump(mode="python"))
        self._repository.save(validated)


# --- Abbildung der alten Bibliothek --------------------------------------

_COUNTRY_NAMES = {
    "germany": "DE",
    "deutschland": "DE",
    "austria": "AT",
    "oesterreich": "AT",
    "österreich": "AT",
    "switzerland": "CH",
    "schweiz": "CH",
}
_GENDERS = {"male", "female", "nonbinary", "other"}
_MBTI = {
    "INTJ", "INTP", "ENTJ", "ENTP", "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ", "ISTP", "ISFP", "ESTP", "ESFP",
}


def _legacy_entry_id(template_id: str) -> str:
    """Stabile Eintragskennung je Vorlage (macht die Uebernahme idempotent)."""
    digest = hashlib.sha1(
        template_id.encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    return f"{PERSONA_SET_ENTRY_ID_PREFIX}{digest[:PERSONA_SET_ID_HEX_LENGTH]}"


class _Mapper:
    """Sammelt die Warnungen einer Vorlage und protokolliert sie je Feld."""

    def __init__(self, template_id: str) -> None:
        self.template_id = template_id or "-"
        self.warnings = 0

    def warn(self, field: str, reason: str, value: Any) -> None:
        self.warnings += 1
        logger.warning(
            "persona_set.legacy_import template_id=%s field=%s reason=%s value=%s",
            self.template_id,
            field,
            reason,
            repr(value)[:80],
        )

    def text(self, raw: Any, field: str, limit: int) -> Optional[str]:
        if raw is None or raw == "":
            return None
        if not isinstance(raw, str):
            self.warn(field, "not_a_string", raw)
            return None
        value = raw.strip()
        if len(value) > limit:
            self.warn(field, f"truncated_to_{limit}", value[:20])
            value = value[:limit]
        return value or None


def _map_legacy_template(
    template: Dict[str, Any], taken_usernames: set[str]
) -> Optional[tuple[PersonaSetProfile, PersonaOrigin, Optional[str], str, int]]:
    """Bildet eine Vorlage auf Profil, Herkunft, Entitaetsverweis und Zeit ab.

    ``None``, wenn die Vorlage sich nicht abbilden laesst (weder ``username``
    noch ``name`` noch ``persona``); der Aufrufer zaehlt sie als uebersprungen.
    """
    template_id = str(template.get("template_id") or "")
    m = _Mapper(template_id)

    username = m.text(template.get("username"), "username", 64)
    name = m.text(template.get("name"), "name", 120)
    persona = m.text(template.get("persona"), "persona", 12000) or ""
    if not (username or name or persona):
        logger.warning(
            "persona_set.legacy_import template_id=%s skipped=true "
            "reason=no_username_name_or_persona",
            m.template_id,
        )
        return None
    username = username or (f"persona_{template_id[:8]}" if template_id else "persona")
    name = name or username

    base = username
    suffix = 1
    while _username_key(username) in taken_usernames:
        suffix += 1
        tail = f"_{suffix}"
        username = f"{base[: 64 - len(tail)]}{tail}"
    if username != base:
        m.warn("username", "renamed_duplicate", base)

    age: Optional[int] = None
    raw_age = template.get("age")
    if raw_age not in (None, ""):
        try:
            candidate = int(str(raw_age).strip())
        except ValueError:
            candidate = -1
        if isinstance(raw_age, bool) or not 0 <= candidate <= 120:
            m.warn("age", "not_in_0_120", raw_age)
        else:
            age = candidate

    gender: Optional[str] = None
    raw_gender = template.get("gender")
    if raw_gender not in (None, ""):
        if isinstance(raw_gender, str) and raw_gender.strip().lower() in _GENDERS:
            gender = raw_gender.strip().lower()
        else:
            m.warn("gender", "not_in_vocabulary", raw_gender)

    mbti: Optional[str] = None
    raw_mbti = template.get("mbti")
    if raw_mbti not in (None, ""):
        if isinstance(raw_mbti, str) and raw_mbti.strip().upper() in _MBTI:
            mbti = raw_mbti.strip().upper()
        else:
            m.warn("mbti", "not_a_valid_type", raw_mbti)

    country: Optional[str] = None
    raw_country = template.get("country")
    if raw_country not in (None, ""):
        text = raw_country.strip() if isinstance(raw_country, str) else ""
        if len(text) == 2 and text.isalpha():
            country = text.upper()
        elif text.lower() in _COUNTRY_NAMES:
            country = _COUNTRY_NAMES[text.lower()]
            m.warn("country", "mapped_name_to_code", raw_country)
        else:
            m.warn("country", "not_an_iso_2_code", raw_country)

    topics: List[str] = []
    raw_topics = template.get("interested_topics")
    if isinstance(raw_topics, list):
        topics = [str(t).strip() for t in raw_topics if str(t).strip()]
        if len(topics) > 15:
            m.warn("interested_topics", "truncated_to_15", len(topics))
            topics = topics[:15]
    elif raw_topics not in (None, ""):
        m.warn("interested_topics", "not_a_list", raw_topics)

    activity: Optional[float] = None
    raw_activity = template.get("activity_level")
    if raw_activity not in (None, ""):
        if (
            isinstance(raw_activity, (int, float))
            and not isinstance(raw_activity, bool)
            and 0.0 <= float(raw_activity) <= 1.0
        ):
            activity = float(raw_activity)
        else:
            m.warn("activity_level", "not_in_0_1", raw_activity)

    kind = template.get("persona_kind")
    persona_kind = "individual"
    if kind in ("individual", "collective"):
        persona_kind = kind
    elif kind not in (None, ""):
        m.warn("persona_kind", "unknown_value", kind)

    source_uuid = m.text(template.get("source_entity_uuid"), "source_entity_uuid", 128)

    profile = PersonaSetProfile.model_validate(
        {
            "username": username,
            "name": name,
            "bio": m.text(template.get("bio"), "bio", 500) or "",
            "persona": persona,
            "age": age,
            "gender": gender,
            "mbti": mbti,
            "country": country,
            "profession": m.text(template.get("profession"), "profession", 200),
            "interested_topics": topics,
            "source_entity_type": m.text(
                template.get("source_entity_type"), "source_entity_type", 120
            ),
            "persona_kind": persona_kind,
            "language": m.text(template.get("language"), "language", 16),
            "activity_level": activity,
            "time_zone": m.text(template.get("time_zone"), "time_zone", 64),
            "location": m.text(template.get("location"), "location", 200),
            "verified": template.get("verified") is True,
        }
    )

    created_at = _now()
    raw_created = template.get("created_at")
    if isinstance(raw_created, str):
        try:
            datetime.fromisoformat(raw_created)
            created_at = raw_created
        except ValueError:
            m.warn("created_at", "not_iso_8601", raw_created)

    origin: PersonaOrigin = "graph" if source_uuid else "manual"
    return profile, origin, source_uuid, created_at, m.warnings


__all__ = [
    "LEGACY_IMPORT_SET_ID",
    "LEGACY_IMPORT_SET_NAME",
    "LegacyImportResult",
    "PersonaSetConflict",
    "PersonaSetEmpty",
    "PersonaSetEntryNotFound",
    "PersonaSetError",
    "PersonaSetLocked",
    "PersonaSetNotFound",
    "PersonaSetService",
]
