"""Tests für Role-Leakage-Erkennung (Issue #1323, Slice 5.1).

Prüft die fünf Beispiele aus dem Issue, Gegenproben und die Robustheit
des Parsers (round_end-Events, kaputte Zeilen, Summary-Raten).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from app.services.sim.role_leakage import (
    audit_sim_dir,
    check_action,
    _extract_self_references,
    _extract_name_signatures,
)
from app.contracts.role_leakage_contract import RoleConflict, RoleLeakageSummary


# ---------------------------------------------------------------------------
# Hilfs-Fixtures
# ---------------------------------------------------------------------------


def _make_persona(
    name: str,
    profession: Optional[str] = None,
    source_entity_type: Optional[str] = None,
    bio: str = "",
    user_id: int = 0,
) -> dict:
    return {
        "user_id": user_id,
        "name": name,
        "profession": profession,
        "source_entity_type": source_entity_type,
        "bio": bio,
    }


def _check(
    *,
    agent_name: str,
    own_persona: dict,
    all_personas: list[dict],
    action_type: str = "CREATE_POST",
    content: str,
    quote_content: Optional[str] = None,
) -> Optional[RoleConflict]:
    """Wrapper um check_action für Tests."""
    action_args: dict = {}
    if action_type == "QUOTE_POST":
        action_args["quote_content"] = quote_content or content
    else:
        action_args["content"] = content
    return check_action(
        platform="reddit",
        round_num=1,
        agent_id=own_persona.get("user_id", 0),
        agent_name=agent_name,
        action_type=action_type,
        action_args=action_args,
        own_persona=own_persona,
        all_personas=all_personas,
    )


# ---------------------------------------------------------------------------
# Beispiel 1: Kaufmännischer Geschäftsführer / "Aus Sicht des Technischen Dienstes"
# ---------------------------------------------------------------------------


class TestKaufmaennischerGeschaeftsfuehrer:
    """Kaufmännischer Geschäftsführer schreibt fremde Perspektive (Technischer Dienst)."""

    def setup_method(self) -> None:
        self.kaufm_gf = _make_persona(
            name="Max Kaufmann",
            profession="Kaufmännischer Geschäftsführer",
            user_id=0,
        )
        self.tech_dienst = _make_persona(
            name="Anna Technik",
            profession="Technischer Dienst",
            user_id=1,
        )
        self.all_personas = [self.kaufm_gf, self.tech_dienst]

    def test_foreign_role_detected(self) -> None:
        result = _check(
            agent_name="Kaufmännischer Geschäftsführer",
            own_persona=self.kaufm_gf,
            all_personas=self.all_personas,
            content="Aus Sicht des Technischen Dienstes ist die Implementierung unproblematisch.",
        )
        assert result is not None
        assert result.reason == "foreign_role"
        assert "Technischen" in result.self_reference or "Technisch" in result.self_reference

    def test_no_conflict_own_role(self) -> None:
        result = _check(
            agent_name="Kaufmännischer Geschäftsführer",
            own_persona=self.kaufm_gf,
            all_personas=self.all_personas,
            content="Aus Sicht des Kaufmännischen Geschäftsführers ist die Kostenfrage entscheidend.",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Beispiel 2: Betriebsrat / "Aus Sicht des Tier-3/Tier-4-Engineering-Supports"
# ---------------------------------------------------------------------------


class TestBetriebsrat:
    """Betriebsrat schreibt aus fremder Engineering-Support-Perspektive."""

    def setup_method(self) -> None:
        self.betriebsrat = _make_persona(
            name="Klaus Betrieb",
            profession="Betriebsrat",
            user_id=0,
        )
        self.eng_support = _make_persona(
            name="Petra Engineering",
            profession="Tier-3/Tier-4-Engineering-Support",
            user_id=1,
        )
        self.all_personas = [self.betriebsrat, self.eng_support]

    def test_foreign_role_detected(self) -> None:
        result = _check(
            agent_name="Betriebsrat",
            own_persona=self.betriebsrat,
            all_personas=self.all_personas,
            content="Aus Sicht des Tier-3/Tier-4-Engineering-Supports fehlen hier die Ressourcen.",
        )
        assert result is not None
        assert result.reason == "foreign_role"

    def test_no_conflict_own_profession(self) -> None:
        result = _check(
            agent_name="Betriebsrat",
            own_persona=self.betriebsrat,
            all_personas=self.all_personas,
            content="Aus Sicht des Betriebsrats sind die Arbeitnehmerrechte zu wahren.",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Beispiel 3: Datenschutzbeauftragte / "Als Chefarzt unserer zentralen Notaufnahme"
# ---------------------------------------------------------------------------


class TestDatenschutzbeauftragte:
    """Datenschutzbeauftragte schreibt aus fremder Chefarzt-Perspektive."""

    def setup_method(self) -> None:
        self.dsb = _make_persona(
            name="Maria Datenschutz",
            profession="Datenschutzbeauftragte",
            source_entity_type="DatenschutzAmt",
            user_id=0,
        )
        self.chefarzt = _make_persona(
            name="Dr. Schmidt",
            profession="Chefarzt Notaufnahme",
            source_entity_type="Krankenhaus",
            user_id=1,
        )
        self.all_personas = [self.dsb, self.chefarzt]

    def test_foreign_role_detected(self) -> None:
        result = _check(
            agent_name="Datenschutzbeauftragte",
            own_persona=self.dsb,
            all_personas=self.all_personas,
            content="Als Chefarzt unserer zentralen Notaufnahme sehen wir täglich die Folgen.",
        )
        assert result is not None
        assert result.reason == "foreign_role"
        assert result.matched_role is not None

    def test_own_role_no_conflict(self) -> None:
        """Als Chefärztin der Notaufnahme bei Persona Chefarzt Notaufnahme → kein Konflikt."""
        chefarzt_persona = _make_persona(
            name="Dr. Andrea Schmidt",
            profession="Chefärztin Notaufnahme",
            source_entity_type="Krankenhaus",
            user_id=0,
        )
        result = _check(
            agent_name="Chefärztin Notaufnahme",
            own_persona=chefarzt_persona,
            all_personas=[chefarzt_persona, self.dsb],
            content="Als Chefärztin der Notaufnahme ist mir die Patientensicherheit oberstes Gebot.",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Beispiel 4: Pflegekräfte / "Als Projektleiterin an der Schnittstelle"
# ---------------------------------------------------------------------------


class TestPflegekraefte:
    """Pflegepersonal schreibt aus Projektleitungs-Perspektive."""

    def setup_method(self) -> None:
        self.pflege = _make_persona(
            name="Pflege Kollektiv",
            profession="Pflegekräfte",
            source_entity_type="Pflegestation",
            user_id=0,
        )
        self.projektleiterin = _make_persona(
            name="Sandra Projekt",
            profession="Projektleiterin IT",
            user_id=1,
        )
        self.all_personas = [self.pflege, self.projektleiterin]

    def test_foreign_role_detected(self) -> None:
        result = _check(
            agent_name="Pflegekräfte",
            own_persona=self.pflege,
            all_personas=self.all_personas,
            content="Als Projektleiterin an der Schnittstelle zwischen IT und Pflege sehen wir Lücken.",
        )
        assert result is not None
        assert result.reason in ("foreign_role", "unmatched_self_reference")


# ---------------------------------------------------------------------------
# Beispiel 5: Chefarzt mit weiblicher Namens-Signatur
# ---------------------------------------------------------------------------


class TestNamensSignatur:
    """Chefarzt-Persona endet Post mit fremdem Frauennamen."""

    def setup_method(self) -> None:
        self.chefarzt = _make_persona(
            name="Dr. Heinrich Müller",
            profession="Chefarzt Kardiologie",
            user_id=0,
        )
        self.fremde_person = _make_persona(
            name="Dr. Lisa Wagner",
            profession="Oberärztin",
            user_id=1,
        )
        self.all_personas = [self.chefarzt, self.fremde_person]

    def test_foreign_name_signature_detected(self) -> None:
        content = "Die Ergebnisse sind eindeutig und sprechen für die neue Methode.\n— Dr. Lisa Wagner"
        result = _check(
            agent_name="Dr. Heinrich Müller",
            own_persona=self.chefarzt,
            all_personas=self.all_personas,
            content=content,
        )
        assert result is not None
        assert result.reason == "foreign_name_signature"

    def test_own_name_signature_no_conflict(self) -> None:
        content = "Ich empfehle die neue Behandlungsmethode uneingeschränkt.\n— Dr. Heinrich Müller"
        result = _check(
            agent_name="Dr. Heinrich Müller",
            own_persona=self.chefarzt,
            all_personas=self.all_personas,
            content=content,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Gegenproben: Generische Phrasen
# ---------------------------------------------------------------------------


class TestGenerischePhrasen:
    """Generische Phrasen dürfen keinen Konflikt auslösen."""

    def setup_method(self) -> None:
        self.persona = _make_persona(name="Test User", profession="Projektmanager", user_id=0)
        self.other = _make_persona(name="Other Person", profession="Entwickler", user_id=1)
        self.all_personas = [self.persona, self.other]

    @pytest.mark.parametrize(
        "content",
        [
            "Als Unternehmen müssen wir die Kosten im Blick behalten.",
            "Als Beispiel sei hier die Einführung neuer Software genannt.",
            "Aus Sicht der Praxis ist das kaum umsetzbar.",
            "Als nächstes werden wir die Ergebnisse auswerten.",
            "Wir als Team stehen hinter dieser Entscheidung.",
        ],
    )
    def test_generic_phrase_no_conflict(self, content: str) -> None:
        result = _check(
            agent_name="Test User",
            own_persona=self.persona,
            all_personas=self.all_personas,
            content=content,
        )
        assert result is None, f"False positive für: {content!r}"


# ---------------------------------------------------------------------------
# QUOTE_POST: liest quote_content, nicht content
# ---------------------------------------------------------------------------


class TestQuotePost:
    """QUOTE_POST soll quote_content auswerten, original_content ignorieren."""

    def setup_method(self) -> None:
        self.persona_a = _make_persona(name="Person A", profession="Arzt", user_id=0)
        self.persona_b = _make_persona(name="Person B", profession="Ingenieur", user_id=1)
        self.all_personas = [self.persona_a, self.persona_b]

    def test_quote_content_triggers_detection(self) -> None:
        """Eigener Kommentar (quote_content) enthält fremde Rolle → Konflikt."""
        result = check_action(
            platform="twitter",
            round_num=2,
            agent_id=0,
            agent_name="Person A",
            action_type="QUOTE_POST",
            action_args={
                "post_id": "123",
                "quote_content": "Als Ingenieur sehe ich das technisch anders.",
                # original_content ist fremder Text → nicht auswerten
                "original_content": "Als Arzt empfehle ich die konservative Therapie.",
            },
            own_persona=self.persona_a,
            all_personas=self.all_personas,
        )
        assert result is not None
        assert result.reason == "foreign_role"

    def test_original_content_ignored(self) -> None:
        """Fremde Rolle nur in original_content (fremder Text) → kein Konflikt."""
        result = check_action(
            platform="twitter",
            round_num=2,
            agent_id=0,
            agent_name="Person A",
            action_type="QUOTE_POST",
            action_args={
                "post_id": "123",
                "quote_content": "Ich stimme dem zu, sehr interessant.",
                "original_content": "Als Ingenieur sehe ich das technisch anders.",
            },
            own_persona=self.persona_a,
            all_personas=self.all_personas,
        )
        assert result is None

    def test_non_text_action_ignored(self) -> None:
        """LIKE_POST und ähnliche Aktionen werden nicht analysiert."""
        result = check_action(
            platform="twitter",
            round_num=1,
            agent_id=0,
            agent_name="Person A",
            action_type="LIKE_POST",
            action_args={"post_id": "123"},
            own_persona=self.persona_a,
            all_personas=self.all_personas,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Robustheit: round_end und kaputte Zeilen überspringen
# ---------------------------------------------------------------------------


class TestRobustness:
    """Robustheit beim Parsen von JSONL-Logs."""

    def test_audit_skips_round_end_and_broken_lines(self, tmp_path: Path) -> None:
        """round_end-Events und kaputte JSON-Zeilen werden übersprungen."""
        sim_dir = tmp_path / "sim_test"
        reddit_dir = sim_dir / "reddit"
        reddit_dir.mkdir(parents=True)

        persona_a = _make_persona(name="Agent A", profession="Arzt", user_id=0)
        persona_b = _make_persona(name="Agent B", profession="Pfleger", user_id=1)
        all_personas = [persona_a, persona_b]

        # Profil-Datei schreiben
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps(all_personas), encoding="utf-8"
        )

        lines = [
            # round_end-Event → überspringen
            json.dumps({"event_type": "round_end", "round": 1}),
            # Kaputte Zeile → überspringen
            "NICHT_JSON{{broken",
            # Leere Zeile → überspringen
            "",
            # Gültige Aktion ohne Rollenkonflikt
            json.dumps({
                "round": 1,
                "agent_id": 0,
                "agent_name": "Agent A",
                "action_type": "CREATE_POST",
                "action_args": {"content": "Ich freue mich auf die Zusammenarbeit."},
                "result": None,
                "success": True,
            }),
        ]
        (reddit_dir / "actions.jsonl").write_text("\n".join(lines), encoding="utf-8")

        summary = audit_sim_dir(sim_dir)
        reddit_summary = next(
            (p for p in summary.per_platform if p.platform == "reddit"), None
        )
        assert reddit_summary is not None
        assert reddit_summary.text_actions == 1
        assert reddit_summary.conflicts == 0

    def test_audit_counts_text_actions_correctly(self, tmp_path: Path) -> None:
        """Nur CREATE_POST/CREATE_COMMENT/QUOTE_POST zählen als texttragende Aktionen."""
        sim_dir = tmp_path / "sim_count"
        reddit_dir = sim_dir / "reddit"
        reddit_dir.mkdir(parents=True)

        persona_a = _make_persona(name="Agent A", profession="Arzt", user_id=0)
        persona_b = _make_persona(name="Agent B", profession="Pfleger", user_id=1)

        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([persona_a, persona_b]), encoding="utf-8"
        )

        lines = [
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Agent A",
                "action_type": "CREATE_POST",
                "action_args": {"content": "Normaler Post ohne Konflikt."},
                "result": None, "success": True,
            }),
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Agent A",
                "action_type": "LIKE_POST",
                "action_args": {"post_id": "999"},
                "result": None, "success": True,
            }),
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Agent A",
                "action_type": "CREATE_COMMENT",
                "action_args": {"content": "Danke für den Hinweis."},
                "result": None, "success": True,
            }),
        ]
        (reddit_dir / "actions.jsonl").write_text("\n".join(lines), encoding="utf-8")

        summary = audit_sim_dir(sim_dir)
        reddit_summary = next(
            (p for p in summary.per_platform if p.platform == "reddit"), None
        )
        assert reddit_summary is not None
        assert reddit_summary.text_actions == 2  # CREATE_POST + CREATE_COMMENT
        assert reddit_summary.conflicts == 0


# ---------------------------------------------------------------------------
# Summary-Raten-Validierung
# ---------------------------------------------------------------------------


class TestSummaryRates:
    """Summary-Raten werden korrekt berechnet."""

    def test_rate_calculation(self, tmp_path: Path) -> None:
        """2 von 4 Aktionen sind Konflikte → Rate 0.5."""
        sim_dir = tmp_path / "sim_rate"
        reddit_dir = sim_dir / "reddit"
        reddit_dir.mkdir(parents=True)

        persona_a = _make_persona(name="Kaufm. GF", profession="Kaufmännischer Geschäftsführer", user_id=0)
        persona_b = _make_persona(name="Tech Dienst", profession="Technischer Dienst", user_id=1)

        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([persona_a, persona_b]), encoding="utf-8"
        )

        lines = [
            # Konflikt 1
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Kaufm. GF",
                "action_type": "CREATE_POST",
                "action_args": {"content": "Aus Sicht des Technischen Dienstes ist das klar."},
                "result": None, "success": True,
            }),
            # Kein Konflikt
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Kaufm. GF",
                "action_type": "CREATE_POST",
                "action_args": {"content": "Wir freuen uns auf die Zusammenarbeit."},
                "result": None, "success": True,
            }),
            # Konflikt 2
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Kaufm. GF",
                "action_type": "CREATE_COMMENT",
                "action_args": {"content": "Als Technischer Dienst sehen wir das Problem."},
                "result": None, "success": True,
            }),
            # Kein Konflikt
            json.dumps({
                "round": 1, "agent_id": 0, "agent_name": "Kaufm. GF",
                "action_type": "CREATE_COMMENT",
                "action_args": {"content": "Das Budget ist das zentrale Thema."},
                "result": None, "success": True,
            }),
        ]
        (reddit_dir / "actions.jsonl").write_text("\n".join(lines), encoding="utf-8")

        summary = audit_sim_dir(sim_dir)
        reddit_summary = next(
            (p for p in summary.per_platform if p.platform == "reddit"), None
        )
        assert reddit_summary is not None
        assert reddit_summary.text_actions == 4
        assert reddit_summary.conflicts == 2
        assert abs(reddit_summary.rate - 0.5) < 0.01

    def test_zero_text_actions_rate(self, tmp_path: Path) -> None:
        """Bei 0 texttragenden Aktionen ist die Rate 0.0 (kein ZeroDivisionError)."""
        sim_dir = tmp_path / "sim_empty"
        reddit_dir = sim_dir / "reddit"
        reddit_dir.mkdir(parents=True)

        (sim_dir / "reddit_profiles.json").write_text("[]", encoding="utf-8")
        (reddit_dir / "actions.jsonl").write_text(
            json.dumps({"event_type": "round_end", "round": 1}), encoding="utf-8"
        )

        summary = audit_sim_dir(sim_dir)
        assert summary.rate == 0.0

    def test_summary_pydantic_model_valid(self, tmp_path: Path) -> None:
        """Das Summary-Modell ist ein valides Pydantic-v2-Objekt."""
        sim_dir = tmp_path / "sim_pydantic"
        reddit_dir = sim_dir / "reddit"
        reddit_dir.mkdir(parents=True)

        (sim_dir / "reddit_profiles.json").write_text("[]", encoding="utf-8")
        (reddit_dir / "actions.jsonl").write_text("", encoding="utf-8")

        summary = audit_sim_dir(sim_dir)
        assert isinstance(summary, RoleLeakageSummary)
        # model_dump() muss ohne Exception funktionieren
        data = summary.model_dump()
        assert "conflicts" in data
        assert "rate" in data
        assert "per_platform" in data


# ---------------------------------------------------------------------------
# Pattern-Extraktion direkt testen
# ---------------------------------------------------------------------------


class TestPatternExtraction:
    def test_aus_sicht_des(self) -> None:
        refs = _extract_self_references("Aus Sicht des Technischen Dienstes ist das klar.")
        assert any("Technischen" in r or "Technisch" in r for r in refs)

    def test_als_prefix(self) -> None:
        refs = _extract_self_references("Als Chefarzt unserer zentralen Notaufnahme sehen wir das.")
        assert len(refs) >= 1

    def test_wir_als(self) -> None:
        refs = _extract_self_references("Wir als Betriebsrat lehnen das ab.")
        assert len(refs) >= 1

    def test_name_signature(self) -> None:
        sigs = _extract_name_signatures("Ich stimme zu.\n— Dr. Lisa Wagner")
        assert any("Wagner" in s for s in sigs)

    def test_viele_gruesse_signature(self) -> None:
        sigs = _extract_name_signatures("Beste Grüße.\nViele Grüße, Hans Müller")
        assert any("Müller" in s for s in sigs)


# ---------------------------------------------------------------------------
# Gegenproben aus dem Referenzlauf sim_54c1c2a6a875 (Lead-Review)
# ---------------------------------------------------------------------------

_LAUF_PERSONAS = [
    _make_persona("Laura Wagner", "Dozentin für kaufmännische Umschulung", "Lecturer", user_id=0),
    _make_persona("Tobias Bauer", "Festangestellter Fachdozent für Elektrotechnik", "Lecturer", user_id=1),
    _make_persona("Nora Schulz", "Honorardozentin für IT-Umschulungen", "Lecturer", user_id=2),
    _make_persona("Niklas Schmitz", "IT-Umschüler (Fachinformatiker Anwendungsentwicklung)", "Person", user_id=3),
    _make_persona(
        "Clara Braun",
        "Stellvertretende Betriebsratsvorsitzende bei einem Bildungsträger",
        "WorksCouncil",
        user_id=4,
    ),
]


@pytest.mark.parametrize(
    ("idx", "content"),
    [
        (1, "Genau so sehe ich das. Als Dozent in der Umschulung erlebe ich das täglich."),
        (2, "Als Honorardozentin in der IT-Weiterbildung erlebe ich täglich Druck."),
        (3, "Stark! Als Teilnehmer will ich wissen, was mit meinen Daten passiert."),
        (3, "Als Klasse haben wir das Thema gestern diskutiert."),
    ],
)
def test_eigene_rolle_in_kompositum_oder_synonym_ist_kein_konflikt(idx, content):
    """Fachdozent/Dozent, Honorardozentin, Umschüler/Teilnehmer: eigene Rolle."""
    persona = _LAUF_PERSONAS[idx]
    result = _check(
        agent_name="Agent",
        own_persona=persona,
        all_personas=_LAUF_PERSONAS,
        content=content,
    )
    assert result is None, result


def test_kompositum_mit_gemeinsamem_bestimmungswort_trifft_fremde_rolle():
    """Dozentin schreibt „Als Betriebsratsmitglied" — Rolle der Betriebsrätin."""
    result = _check(
        agent_name="Dozenten",
        own_persona=_LAUF_PERSONAS[0],
        all_personas=_LAUF_PERSONAS,
        content="Das sehe ich genauso. Als Betriebsratsmitglied war es mir wichtig, mitzureden.",
    )
    assert result is not None
    assert result.reason == "foreign_role"
    assert "Betriebsrat" in (result.matched_role or "")


def test_twitter_profile_erben_beruf_aus_reddit_profilen(tmp_path: Path):
    """``twitter_profiles.csv`` hat keinen Beruf — ohne Ergänzung wäre jede
    Selbstreferenz auf Twitter ``unmatched_self_reference``."""
    sim = tmp_path / "sim"
    (sim / "twitter").mkdir(parents=True)
    (sim / "reddit_profiles.json").write_text(
        json.dumps([_LAUF_PERSONAS[2]]), encoding="utf-8"
    )
    (sim / "twitter_profiles.csv").write_text(
        "user_id,name,username,user_char,description\n0,Nora Schulz,nora,,\n",
        encoding="utf-8",
    )
    (sim / "twitter" / "actions.jsonl").write_text(
        json.dumps({
            "round": 1,
            "agent_id": 0,
            "agent_name": "Honorarkräfte",
            "action_type": "CREATE_POST",
            "action_args": {"content": "Als Honorardozentin sehe ich KI als Werkzeug."},
        }) + "\n",
        encoding="utf-8",
    )
    summary = audit_sim_dir(sim)
    assert summary.text_actions == 1
    assert summary.conflicts == 0
