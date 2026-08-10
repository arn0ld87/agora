"""Issue #1186 — das finale Speichern verliert keine Profilfelder mehr.

In 262 persistierten Profilen über sechs Läufe trug kein einziges das Feld
`voice_register` — unabhängig davon, ob es vom LLM (252) oder regelbasiert
(10) erzeugt wurde. Drei der Läufe waren vom selben Tag wie dieser Fix, der
zugehörige Fallback im Generator existiert seit Mai. Der Defekt war also
aktuell, nicht historisch.

**Ursache:** `_save_reddit_json` baute das Dict aus einer handgepflegten
Feldliste neu, statt `to_reddit_format()` zu benutzen — und überschrieb damit
die Datei, die der Realtime-Pfad zuvor korrekt geschrieben hatte. Jedes Feld,
das in dieser Liste fehlte, ging beim finalen Speichern verloren.

#1029 hat dasselbe Muster schon einmal getroffen und damals `generation_source`
nachgetragen; der Kommentar dort beschreibt den Mechanismus präzise. Eine
zweite Einzelnachtragung wäre die dritte Gelegenheit für denselben Fehler
gewesen — deshalb prüfen diese Tests die **Vollständigkeit**, nicht einzelne
Felder.

Blockierte #1009: Der dort vorgeschlagene Join gegen `<platform>_profiles.json`
kann `voice_register` nur auflösen, wenn das Feld in der Datei steht.
"""

from __future__ import annotations

import json

import pytest

from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import OasisProfileGenerator

#: Felder, die OASIS zum Laden der Profile braucht. Sie fehlen in
#: ``to_reddit_format()`` bewusst, wenn sie nicht gesetzt sind — beim
#: Persistieren muss aber ein Wert dastehen.
_OASIS_REQUIRED = ("user_id", "username", "name", "bio", "persona", "age", "gender", "mbti", "country")


@pytest.fixture
def generator() -> OasisProfileGenerator:
    """Generator ohne Graph-Anbindung — der regelbasierte Pfad braucht keine."""
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    gen.storage = None
    gen.graph_id = None
    return gen


def _profile(generator: OasisProfileGenerator, name: str = "Betriebsrat"):
    entity = EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=["Entity", "Stakeholder"],
        summary="Ein Gremium der Beschäftigten.",
        attributes={},
    )
    return generator.generate_profile_from_entity(entity=entity, user_id=0, use_llm=False)


def _persisted(generator: OasisProfileGenerator, profile, tmp_path) -> dict:
    path = tmp_path / "reddit_profiles.json"
    generator._save_reddit_json([profile], str(path))
    return json.loads(path.read_text(encoding="utf-8"))[0]


class TestNoFieldIsLostOnSave:
    def test_kein_feld_aus_dem_format_faellt_beim_speichern_heraus(
        self, generator: OasisProfileGenerator, tmp_path
    ) -> None:
        """Der eigentliche Regressionsanker.

        Geprüft wird die Vollständigkeit, nicht eine Liste bekannter Felder:
        kommt morgen ein Feld zu ``to_reddit_format()`` dazu, muss es
        automatisch mitpersistiert werden. Genau daran ist der Defekt zweimal
        vorbeigelaufen (#1029, #1186).
        """
        profile = _profile(generator)
        in_format = set(profile.to_reddit_format())

        persisted = set(_persisted(generator, profile, tmp_path))

        missing = in_format - persisted
        assert not missing, (
            f"Diese Felder gehen beim finalen Speichern verloren: {sorted(missing)}. "
            "_save_reddit_json baut das Dict vermutlich wieder aus einer eigenen "
            "Feldliste statt aus to_reddit_format()."
        )

    def test_voice_register_landet_in_der_datei(
        self, generator: OasisProfileGenerator, tmp_path
    ) -> None:
        """Der gemeldete Fall — explizit, weil er #1009 blockiert hat."""
        persisted = _persisted(generator, _profile(generator), tmp_path)

        assert persisted.get("voice_register"), (
            "Ohne dieses Feld kann der Feed-Snapshot (#1009) die Stimmlage "
            "nicht aufloesen, und ein erfundener Wert waere eine Falschaussage."
        )

    def test_die_herkunftskennzeichnung_bleibt_erhalten(
        self, generator: OasisProfileGenerator, tmp_path
    ) -> None:
        """Gegenprobe für #1029: die damals nachgetragene Angabe darf durch
        die Umstellung nicht wieder verschwinden."""
        persisted = _persisted(generator, _profile(generator), tmp_path)

        assert persisted.get("generation_source") == "rule_based"


class TestOasisRequirementsStillHold:
    @pytest.mark.parametrize("field", _OASIS_REQUIRED)
    def test_die_pflichtfelder_haben_weiterhin_einen_wert(
        self, generator: OasisProfileGenerator, tmp_path, field: str
    ) -> None:
        """``to_reddit_format()`` lässt nicht gesetzte Felder weg — OASIS
        braucht sie aber. Die Defaults dürfen durch die Umstellung nicht
        wegfallen."""
        persisted = _persisted(generator, _profile(generator), tmp_path)

        assert field in persisted, f"OASIS-Pflichtfeld {field} fehlt in der Datei"
        assert persisted[field] not in (None, ""), f"{field} ist leer"

    def test_ein_profil_ohne_optionale_angaben_bekommt_die_defaults(
        self, generator: OasisProfileGenerator, tmp_path
    ) -> None:
        """Der Fall, für den die Defaults da sind: ein dünnes Profil."""
        from app.services.oasis_profile_generator import OasisAgentProfile

        bare = OasisAgentProfile(
            user_id=0,
            user_name="ohne_angaben",
            name="Ohne Angaben",
            bio="",
            persona="",
        )

        persisted = _persisted(generator, bare, tmp_path)

        assert persisted["age"] == 30
        assert persisted["mbti"] == "ISTJ"
        assert persisted["country"] == "US"
        assert persisted["karma"] == 1000
        assert persisted["bio"], "leere bio muss durch den Namen ersetzt werden"

    def test_die_user_id_faellt_auf_den_index_zurueck(
        self, generator: OasisProfileGenerator, tmp_path
    ) -> None:
        """``user_id`` ist der Schlüssel für ``agent_graph.get_agent()`` —
        ohne ihn findet OASIS den Agenten nicht."""
        from app.services.oasis_profile_generator import OasisAgentProfile

        profile = OasisAgentProfile(
            user_id=None, user_name="x", name="X", bio="b", persona="p"
        )
        path = tmp_path / "reddit_profiles.json"
        generator._save_reddit_json([profile, profile], str(path))
        persisted = json.loads(path.read_text(encoding="utf-8"))

        assert [entry["user_id"] for entry in persisted] == [0, 1]

    def test_die_bio_wird_gekuerzt(
        self, generator: OasisProfileGenerator, tmp_path
    ) -> None:
        from app.services.oasis_profile_generator import OasisAgentProfile

        profile = OasisAgentProfile(
            user_id=0, user_name="x", name="X", bio="A" * 400, persona="p"
        )

        persisted = _persisted(generator, profile, tmp_path)

        assert len(persisted["bio"]) == 150
