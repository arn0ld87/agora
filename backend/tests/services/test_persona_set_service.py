"""Tests fuer ``app.services.persona_set_service`` (Issue #1807, Slice 7b).

Arbeitet gegen den Dateiadapter in ``tmp_path`` und eine In-Memory-Ablage fuer
die alte Persona-Bibliothek. Kein Netz, kein LLM.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.contracts.persona_set_contract import (
    PersonaSetCreate,
    PersonaSetDuplicate,
    PersonaSetEntryCreate,
    PersonaSetEntryUpdate,
    PersonaSetProfile,
    PersonaSetUpdate,
)
from app.services.artifact_store import InMemoryArtifactStore
from app.services.file_persona_set_store import FilePersonaSetRepository
from app.services.persona_library import PersonaLibrary
from app.services.persona_set_service import (
    LEGACY_IMPORT_SET_ID,
    PersonaSetConflict,
    PersonaSetEmpty,
    PersonaSetEntryNotFound,
    PersonaSetLocked,
    PersonaSetNotFound,
    PersonaSetService,
)


@pytest.fixture
def service(tmp_path: Path) -> PersonaSetService:
    return PersonaSetService(FilePersonaSetRepository(str(tmp_path / "persona_sets")))


def _entry(username: str, origin: str = "manual", **profile) -> PersonaSetEntryCreate:
    return PersonaSetEntryCreate(
        origin=origin,
        profile=PersonaSetProfile(username=username, name=username.title(), **profile),
    )


def _set_with(service: PersonaSetService, *usernames: str):
    record = service.create_set(PersonaSetCreate(name="Betroffene"))
    for username in usernames:
        service.add_entry(record.id, _entry(username))
    return service.get_set(record.id)


# --- Saetze ---------------------------------------------------------------


def test_create_set_vergibt_kennung_und_startet_leer(service):
    record = service.create_set(
        PersonaSetCreate(name="  Pflege  ", description="Quelle: Gutachten")
    )

    assert record.id.startswith("pset_")
    assert record.name == "Pflege"
    assert record.entries == []
    assert record.locked_at is None
    assert record.used_by_simulation_ids == []


def test_list_sets_liefert_kacheln_neueste_zuerst(service):
    first = service.create_set(PersonaSetCreate(name="A"))
    second = service.create_set(PersonaSetCreate(name="B"))
    service.add_entry(second.id, _entry("anna"))

    summaries = service.list_sets()

    assert {s.id for s in summaries} == {first.id, second.id}
    by_id = {s.id: s for s in summaries}
    assert by_id[second.id].entry_count == 1
    assert by_id[first.id].locked is False


def test_get_set_unbekannt_wirft_not_found(service):
    with pytest.raises(PersonaSetNotFound):
        service.get_set("pset_gibtesnicht")


def test_update_set_aendert_name_und_beschreibung(service):
    record = service.create_set(PersonaSetCreate(name="Alt"))

    updated = service.update_set(
        record.id, PersonaSetUpdate(name="Neu", description="Beschreibung")
    )

    assert updated.name == "Neu"
    assert updated.description == "Beschreibung"


def test_delete_set_entfernt_ungesperrten_satz(service):
    record = service.create_set(PersonaSetCreate(name="Weg"))

    service.delete_set(record.id)

    with pytest.raises(PersonaSetNotFound):
        service.get_set(record.id)


# --- Eintraege ------------------------------------------------------------


def test_add_entry_vergibt_kennung_und_haelt_herkunft(service):
    record = service.create_set(PersonaSetCreate(name="S"))

    entry = service.add_entry(record.id, _entry("anna", origin="fallback"))

    assert entry.entry_id.startswith("pent_")
    assert entry.origin == "fallback"
    stored = service.get_set(record.id).entries
    assert [e.entry_id for e in stored] == [entry.entry_id]
    assert stored[0].origin == "fallback"


def test_username_ist_im_satz_eindeutig_auch_bei_anderer_schreibweise(service):
    record = _set_with(service, "anna")

    with pytest.raises(PersonaSetConflict):
        service.add_entry(record.id, _entry("ANNA"))

    assert len(service.get_set(record.id).entries) == 1


def test_gleicher_username_in_anderem_satz_ist_erlaubt(service):
    first = _set_with(service, "anna")
    second = service.create_set(PersonaSetCreate(name="Zweiter"))

    service.add_entry(second.id, _entry("anna"))

    assert len(service.get_set(first.id).entries) == 1
    assert len(service.get_set(second.id).entries) == 1


def test_update_entry_ersetzt_profil_und_kollidiert_nicht_mit_sich_selbst(service):
    record = _set_with(service, "anna", "bernd")
    anna, bernd = record.entries

    same_name = service.update_entry(
        record.id,
        anna.entry_id,
        PersonaSetEntryUpdate(
            profile=PersonaSetProfile(username="anna", name="Anna Neu", bio="neu")
        ),
    )
    assert same_name.profile.name == "Anna Neu"
    assert same_name.entry_id == anna.entry_id

    with pytest.raises(PersonaSetConflict):
        service.update_entry(
            record.id,
            bernd.entry_id,
            PersonaSetEntryUpdate(
                profile=PersonaSetProfile(username="Anna", name="Bernd")
            ),
        )


def test_update_entry_nur_herkunft_laesst_profil_stehen(service):
    record = _set_with(service, "anna")
    entry = record.entries[0]

    updated = service.update_entry(
        record.id, entry.entry_id, PersonaSetEntryUpdate(origin="ai_draft")
    )

    assert updated.origin == "ai_draft"
    assert updated.profile == entry.profile


def test_update_entry_unbekannt_wirft_entry_not_found(service):
    record = _set_with(service, "anna")

    with pytest.raises(PersonaSetEntryNotFound):
        service.update_entry(
            record.id, "pent_nein", PersonaSetEntryUpdate(origin="manual")
        )


def test_delete_entries_ist_alles_oder_nichts(service):
    record = _set_with(service, "anna", "bernd", "carla")
    anna, bernd, carla = record.entries

    with pytest.raises(PersonaSetEntryNotFound):
        service.delete_entries(record.id, [anna.entry_id, "pent_nein"])
    assert len(service.get_set(record.id).entries) == 3

    summary = service.delete_entries(record.id, [anna.entry_id, carla.entry_id])

    assert summary.entry_count == 1
    assert [e.entry_id for e in service.get_set(record.id).entries] == [bernd.entry_id]


def test_delete_entry_einzeln(service):
    record = _set_with(service, "anna", "bernd")

    summary = service.delete_entry(record.id, record.entries[0].entry_id)

    assert summary.entry_count == 1


# --- Sperre ---------------------------------------------------------------


def test_gesperrter_satz_lehnt_jede_aenderung_der_personas_ab(service):
    record = _set_with(service, "anna", "bernd")
    anna = record.entries[0]
    service.record_run(record.id, "sim_1")

    with pytest.raises(PersonaSetLocked):
        service.add_entry(record.id, _entry("carla"))
    with pytest.raises(PersonaSetLocked):
        service.update_entry(
            record.id, anna.entry_id, PersonaSetEntryUpdate(origin="manual")
        )
    with pytest.raises(PersonaSetLocked):
        service.delete_entry(record.id, anna.entry_id)
    with pytest.raises(PersonaSetLocked):
        service.delete_entries(record.id, [anna.entry_id])
    with pytest.raises(PersonaSetLocked):
        service.delete_set(record.id)

    after = service.get_set(record.id)
    assert [e.entry_id for e in after.entries] == [e.entry_id for e in record.entries]
    assert after.locked_at is not None


def test_gesperrter_satz_laesst_name_und_beschreibung_aendern(service):
    record = _set_with(service, "anna")
    service.record_run(record.id, "sim_1")

    updated = service.update_set(record.id, PersonaSetUpdate(name="Umbenannt"))

    assert updated.name == "Umbenannt"
    assert updated.locked_at is not None
    assert updated.used_by_simulation_ids == ["sim_1"]


def test_record_run_ist_idempotent_und_sammelt_laeufe(service):
    record = _set_with(service, "anna")

    service.record_run(record.id, "sim_1")
    service.record_run(record.id, "sim_1")
    service.record_run(record.id, "sim_2")

    assert service.get_set(record.id).used_by_simulation_ids == ["sim_1", "sim_2"]


def test_record_run_unbekannter_satz_gibt_none(service):
    assert service.record_run("pset_nein", "sim_1") is None


# --- Duplizieren ----------------------------------------------------------


def test_duplicate_set_kopiert_mit_neuen_kennungen_und_ohne_sperre(service):
    record = service.create_set(PersonaSetCreate(name="Original", description="d"))
    service.add_entry(record.id, _entry("anna", origin="graph"))
    service.add_entry(record.id, _entry("bernd", origin="fallback"))
    service.record_run(record.id, "sim_1")
    original = service.get_set(record.id)

    copy = service.duplicate_set(record.id, PersonaSetDuplicate(name="Kopie"))

    assert copy.id != original.id
    assert copy.name == "Kopie"
    assert copy.description == "d"
    assert copy.locked_at is None
    assert copy.used_by_simulation_ids == []
    assert [e.origin for e in copy.entries] == ["graph", "fallback"]
    assert [e.profile for e in copy.entries] == [e.profile for e in original.entries]
    assert not {e.entry_id for e in copy.entries} & {e.entry_id for e in original.entries}
    # Die Kopie ist bearbeitbar, das Original bleibt gesperrt.
    service.add_entry(copy.id, _entry("carla"))
    assert len(service.get_set(original.id).entries) == 2


# --- Lauf aus Satz --------------------------------------------------------


def test_snapshot_profiles_liefert_kopien_im_prepare_format(service):
    record = service.create_set(PersonaSetCreate(name="S"))
    service.add_entry(record.id, _entry("anna", origin="manual", age=41, country="DE"))
    service.add_entry(record.id, _entry("bernd", origin="graph"))

    snapshot = service.snapshot_profiles(record.id)

    assert [p["username"] for p in snapshot] == ["anna", "bernd"]
    assert snapshot[0]["is_manual"] is True
    assert snapshot[1]["is_manual"] is False
    assert snapshot[0]["age"] == 41
    assert snapshot[0]["source_entity_type"] == "persona_set"
    # Veraendern der Kopie darf den Satz nicht beruehren.
    snapshot[0]["username"] = "veraendert"
    assert service.get_set(record.id).entries[0].profile.username == "anna"


def test_snapshot_profiles_leerer_satz_wirft_empty(service):
    record = service.create_set(PersonaSetCreate(name="Leer"))

    with pytest.raises(PersonaSetEmpty):
        service.snapshot_profiles(record.id)


# --- Qualitaet ------------------------------------------------------------


def test_quality_nutzt_die_heuristiken_je_eintrag(service):
    record = service.create_set(PersonaSetCreate(name="S"))
    service.add_entry(
        record.id,
        PersonaSetEntryCreate(
            origin="manual",
            profile=PersonaSetProfile(
                username="anna", name="Anna", bio="b", persona="p", profession="Lehrerin"
            ),
        ),
    )
    service.add_entry(record.id, _entry("leer", origin="ai_draft"))

    report = service.quality(record.id)

    assert report.set_id == record.id
    assert report.summary.total == 2
    assert [p.username for p in report.personas] == ["anna", "leer"]
    by_user = {p.username: {i.code for i in p.issues} for p in report.personas}
    assert "missing_core_fields" in by_user["leer"]
    assert "missing_core_fields" not in by_user["anna"]
    # Handgeschriebene Eintraege sind vom Entitaetsverweis ausgenommen.
    assert "missing_entity_link" not in by_user["anna"]
    assert "missing_entity_link" in by_user["leer"]


def test_quality_leerer_satz_meldet_no_personas(service):
    record = service.create_set(PersonaSetCreate(name="Leer"))

    report = service.quality(record.id)

    assert [i.code for i in report.global_issues] == ["no_personas"]
    assert report.personas == []


# --- Altbestand -----------------------------------------------------------


@pytest.fixture
def library() -> PersonaLibrary:
    return PersonaLibrary(store=InMemoryArtifactStore())


@pytest.fixture
def marker() -> InMemoryArtifactStore:
    return InMemoryArtifactStore()


def _template(library: PersonaLibrary, **fields) -> dict:
    return library.save_template({"username": "anna", "name": "Anna", **fields})


def test_import_legacy_legt_sammelsatz_an_und_mappt_felder(service, library, marker):
    _template(
        library,
        persona="Skeptisch.",
        age=41,
        gender="female",
        mbti="intj",
        country="DE",
        interested_topics="Pflege, Rente",
        source_entity_uuid="uuid-1",
    )
    _template(library, username="bernd", name="Bernd")

    result = service.import_legacy_persona_library(library, marker_store=marker)

    assert result.set_id == LEGACY_IMPORT_SET_ID
    assert result.set_created is True
    assert result.imported == 2
    assert result.skipped == 0
    record = service.get_set(LEGACY_IMPORT_SET_ID)
    assert record.name == "Importiert"
    by_user = {e.profile.username: e for e in record.entries}
    anna = by_user["anna"]
    assert anna.origin == "graph"  # Entitaetsverweis vorhanden
    assert anna.source_entity_uuid == "uuid-1"
    assert anna.profile.mbti == "INTJ"
    assert anna.profile.interested_topics == ["Pflege", "Rente"]
    assert by_user["bernd"].origin == "manual"


def test_import_legacy_ist_idempotent_und_ergaenzt_nur_neues(service, library, marker):
    _template(library)
    service.import_legacy_persona_library(library, marker_store=marker)

    again = service.import_legacy_persona_library(library, marker_store=marker)
    assert again.imported == 0
    assert again.already_present == 1
    assert again.set_created is False
    assert len(service.get_set(LEGACY_IMPORT_SET_ID).entries) == 1

    _template(library, username="bernd", name="Bernd")
    third = service.import_legacy_persona_library(library, marker_store=marker)
    assert third.imported == 1
    assert third.already_present == 1
    assert len(service.get_set(LEGACY_IMPORT_SET_ID).entries) == 2


def test_import_legacy_ergaenzt_nichts_wenn_der_satz_gesperrt_ist(
    service, library, marker
):
    _template(library)
    service.import_legacy_persona_library(library, marker_store=marker)
    service.record_run(LEGACY_IMPORT_SET_ID, "sim_1")
    _template(library, username="bernd", name="Bernd")

    result = service.import_legacy_persona_library(library, marker_store=marker)

    assert result.imported == 0
    assert result.set_locked is True
    assert len(service.get_set(LEGACY_IMPORT_SET_ID).entries) == 1


def test_import_legacy_normalisiert_und_protokolliert_je_vorlage(
    service, library, marker, caplog
):
    template = _template(
        library,
        age=200,
        gender="m",
        mbti="XXXX",
        country="Germany",
        activity_level=3,
    )
    other = _template(library, username="bernd", name="Bernd", country="Atlantis")

    _target = logging.getLogger("agora.persona_sets.service")
    _target.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="agora.persona_sets.service")
    try:
        result = service.import_legacy_persona_library(library, marker_store=marker)
    finally:
        _target.removeHandler(caplog.handler)

    by_user = {
        e.profile.username: e.profile
        for e in service.get_set(LEGACY_IMPORT_SET_ID).entries
    }
    anna = by_user["anna"]
    assert anna.age is None
    assert anna.gender is None
    assert anna.mbti is None
    assert anna.country == "DE"
    assert anna.activity_level is None
    assert by_user["bernd"].country is None
    assert result.normalized_fields >= 6
    messages = "\n".join(r.getMessage() for r in caplog.records)
    for field in ("age", "gender", "mbti", "country", "activity_level"):
        assert f"template_id={template['template_id']} field={field}" in messages
    assert f"template_id={other['template_id']} field=country" in messages


def test_import_legacy_ueberspringt_nicht_abbildbare_vorlage_und_zaehlt(
    service, library, marker, caplog
):
    _template(library)
    # Direkt in die Ablage: save_template ergaenzt immer einen Benutzernamen.
    library._store.write_json(
        "_persona_library",
        "persona_library",
        library.list_templates() + [{"template_id": "tpl_leer", "age": 30}],
    )

    _target = logging.getLogger("agora.persona_sets.service")
    _target.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="agora.persona_sets.service")
    try:
        result = service.import_legacy_persona_library(library, marker_store=marker)
    finally:
        _target.removeHandler(caplog.handler)

    assert result.imported == 1
    assert result.skipped == 1
    assert "template_id=tpl_leer skipped=true" in caplog.text


def test_import_legacy_benennt_doppelte_usernames_um(service, library, marker):
    first = _template(library)
    library._store.write_json(
        "_persona_library",
        "persona_library",
        library.list_templates()
        + [{**first, "template_id": "tpl_zwei", "name": "Anna Zwei"}],
    )

    result = service.import_legacy_persona_library(library, marker_store=marker)

    assert result.imported == 2
    names = sorted(
        e.profile.username for e in service.get_set(LEGACY_IMPORT_SET_ID).entries
    )
    assert names == ["anna", "anna_2"]


def test_import_legacy_ohne_vorlagen_legt_keinen_leeren_satz_an(
    service, library, marker
):
    result = service.import_legacy_persona_library(library, marker_store=marker)

    assert result.set_created is False
    with pytest.raises(PersonaSetNotFound):
        service.get_set(LEGACY_IMPORT_SET_ID)


def test_ensure_legacy_import_laeuft_einmal_und_nicht_nach_loeschen(
    service, library, marker
):
    _template(library)

    first = service.ensure_legacy_import(library, marker_store=marker)
    assert first is not None and first.imported == 1

    assert service.ensure_legacy_import(library, marker_store=marker) is None

    service.delete_set(LEGACY_IMPORT_SET_ID)
    # Marker verhindert, dass das Loeschen rueckgaengig gemacht wird.
    assert service.ensure_legacy_import(library, marker_store=marker) is None
    with pytest.raises(PersonaSetNotFound):
        service.get_set(LEGACY_IMPORT_SET_ID)


def test_ensure_legacy_import_ohne_vorlagen_tut_nichts(service, library, marker):
    assert service.ensure_legacy_import(library, marker_store=marker) is None
    assert service.list_sets() == []
