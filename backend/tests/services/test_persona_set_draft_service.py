"""Tests fuer den KI-Entwurf einer Persona (Issue #1807, Slice 7c).

Der API-Test deckt die HTTP-Kante ab. Hier steht, was der Dienst selbst
verantwortet und was im Prepare-Pfad nicht abgesichert war:

* **Verrechnung.** Jeder Entwurf laeuft als Job ``persona_draft``. Ohne ihn hat
  ``LLMClient`` keinen ``run_id``, also keinen ``RunBudgetEnforcer`` (#984) —
  der Aufruf laege am harten Budget vorbei und stuende in keiner Aktivitaet.
* **Kein Rueckfall.** Der Prepare-Pfad faellt bei LLM-Ausfall auf einen
  regelbasierten Ersatz zurueck (#1029). Beim Entwurf waere das falsch: eine
  erfundene Persona mit der Plakette „KI-Entwurf" ist schlimmer als eine
  sichtbare Fehlermeldung. Der Test haelt fest, dass **kein** Eintrag
  entsteht und der Fehler durchschlaegt.
* **Hartes Budget durchschlaegt** (dieselbe Linie wie PR #1461).
* **Begrenzung.** Der Dienst kuerzt und verwirft, statt dem Editor Felder zu
  geben, die er nicht anzeigen kann.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services import persona_set_draft_service as draft_module
from app.services.persona_set_draft_service import (
    DRAFT_RUN_TYPE,
    PersonaDraftError,
    PersonaDraftRequestModel,
    PersonaDraftUnavailable,
    draft_persona_entry,
)
from app.services.run_budget import BudgetExceededError


class _FakeRegistry:
    """Minimaler RunRegistry-Ersatz: merkt sich Anlage und Abschluss."""

    def __init__(self) -> None:
        self.created: List[Dict[str, Any]] = []
        self.updated: List[Dict[str, Any]] = []

    def create_run(self, run_type: str, entity_id: str, **kwargs: Any) -> Dict[str, Any]:
        self.created.append({"run_type": run_type, "entity_id": entity_id, **kwargs})
        return {"run_id": "run_testdraft"}

    def update_run(self, run_id: str, **kwargs: Any) -> None:
        self.updated.append({"run_id": run_id, **kwargs})


class _FakeLLM:
    """Liefert eine fest vorgegebene Antwort, zaehlt die Aufrufe."""

    instances: List["_FakeLLM"] = []

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id
        self.calls: List[Dict[str, Any]] = []
        self.responses: List[Any] = []
        _FakeLLM.instances.append(self)

    def chat_json(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("keine Antwort hinterlegt")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def registry(monkeypatch):
    fake = _FakeRegistry()
    monkeypatch.setattr(draft_module, "RunRegistry", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def _reset_fake_llm():
    _FakeLLM.instances = []
    yield
    _FakeLLM.instances = []


@pytest.fixture
def install_llm(monkeypatch):
    """Setzt ``_client`` auf einen Fake; gibt eine Funktion zurueck, die die
    Antworten des naechsten Aufrufs vorbelegt.

    Der Client entsteht erst beim Aufruf (``_client(run_id)``), deshalb kann die
    Fixture ihn nicht zurueckgeben — sie liefert den Beleger, und die Tests
    greifen ueber ``_FakeLLM.instances`` darauf zu.
    """

    def install(responses: List[Any]) -> None:
        def factory(run_id: str | None = None) -> _FakeLLM:
            client = _FakeLLM(run_id=run_id)
            client.responses = list(responses)
            return client

        monkeypatch.setattr(draft_module, "_client", factory)

    return install


def _budget_error() -> BudgetExceededError:
    """Der echte Fehler des Run-Budgets (#984).

    Er nimmt nicht eine freie Nachricht, sondern Dimension und Zahlen — die
    stehen in der 409-Antwort der Oberflaeche. Ein Aufruf mit anderer Signatur
    wuerde einen Fehler testen, den der Dienst nie sieht.
    """
    return BudgetExceededError("tokens", observed=1200, threshold=1000)


_GOOD_DRAFT = {
    "username": "KarlaBrandt",
    "name": "Karla Brandt",
    "bio": "Betriebsratin aus Bremen, seit zwei Jahren im Konflikt.",
    "persona": "Spricht sachlich, stellt Rueckfragen, nennt Zahlen.",
    "age": 41,
    "gender": "female",
    "mbti": "INTJ",
    "country": "DE",
    "profession": "Betriebsratin",
    "interested_topics": ["Arbeitsrecht", "Schichtmodelle"],
    "language": "de",
    "activity_level": 0.6,
    "time_zone": "Europe/Berlin",
    "location": "Bremen",
    "example_post": "Die Schichtplanung muss mit dem Betriebsrat abgestimmt sein.",
    "example_network": "twitter",
}


def test_draft_is_billed_to_a_persona_draft_job(registry, install_llm):
    """Ohne Job haette der Aufruf keinen Budget-Enforcer und keine Spur."""
    install_llm([dict(_GOOD_DRAFT)])

    draft_persona_entry(set_id="pset_1", brief="Betriebsratin aus Bremen")

    assert len(registry.created) == 1
    run = registry.created[0]
    assert run["run_type"] == DRAFT_RUN_TYPE
    assert run["entity_id"] == "pset_1"
    assert run["linked_ids"] == {"persona_set_id": "pset_1"}
    # Der Job muss abgeschlossen werden, sonst steht er ewig auf "laeuft".
    assert registry.updated[0]["status"] == "completed"


def test_the_job_id_reaches_the_llm_client(registry, install_llm):
    """``run_id`` ist keine Beobachtungsnummer: der Enforcer haengt daran."""
    install_llm([dict(_GOOD_DRAFT)])

    draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert _FakeLLM.instances[0].run_id == "run_testdraft"


def test_draft_uses_the_persona_context_and_schema(registry, install_llm):
    """Der Aufruf muss als Persona-Kontext gebucht und gegen ein Schema geprueft
    werden — sonst landet er in keiner Auswertung und die Antwort ist ungeprueft."""
    install_llm([dict(_GOOD_DRAFT)])

    draft_persona_entry(set_id="pset_1", brief="Bremen")

    call = _FakeLLM.instances[0].calls[0]
    assert call["context"] == "persona"
    assert call["schema"] is PersonaDraftRequestModel
    assert call["schema_name"] == "persona_draft"
    assert call["force_no_thinking"] is True


def test_draft_carries_the_brief_into_the_prompt(registry, install_llm):
    """Der Brief muss im Prompt stehen, sonst entwirft das Modell irgendeine
    Persona — und die Antwort waere nicht als Entwurf des Auftrags erkennbar."""
    install_llm([dict(_GOOD_DRAFT)])

    draft_persona_entry(set_id="pset_1", brief="Betriebsratin aus Bremen")

    prompt = _FakeLLM.instances[0].calls[0]["messages"][-1]["content"]
    assert "Betriebsratin aus Bremen" in prompt
    assert "de" in prompt


def test_a_provider_failure_leaves_no_draft_and_no_fallback(registry, install_llm):
    """Kein regelbasierter Ersatz: der Aufrufer entscheidet, nicht der Dienst."""
    install_llm([RuntimeError("provider returned 503")] * 2)

    with pytest.raises(PersonaDraftUnavailable) as excinfo:
        draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert "503" in str(excinfo.value)
    # Beide Versuche gerufen — der zweite sieht denselben Brief und kann nichts
    # anderes liefern, aber er muss da sein, sonst waere es ein Zufall.
    assert len(_FakeLLM.instances[0].calls) == 2
    # Und der Job steht auf "failed", nicht auf "laeuft".
    assert registry.updated[-1]["status"] == "failed"


def test_a_hard_budget_stops_immediately(registry, install_llm):
    """Wie im Prepare-Pfad (PR #1461): ein hartes Budget muss durchschlagen und
    darf nicht in einem zweiten Versuch oder einem Ersatzprofil enden."""
    install_llm([_budget_error()] * 2)

    with pytest.raises(BudgetExceededError):
        draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert len(_FakeLLM.instances[0].calls) == 1
    assert registry.updated[-1]["status"] == "failed"


def test_an_unusable_answer_is_a_draft_error(registry, install_llm):
    """Ohne ``username`` entsteht kein Eintrag, an dem man ihn erkennt — das
    ist kein Entwurf, sondern eine Fehlermeldung."""
    install_llm([{"bio": "nur Text, keine Person"}] * 2)

    with pytest.raises(PersonaDraftError):
        draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert registry.updated[-1]["status"] == "failed"


def test_a_transient_failure_is_retried_once(registry, install_llm):
    """Der erste Versuch darf scheitern; der zweite ist der Wiederholungsversuch."""
    install_llm([RuntimeError("timeout"), dict(_GOOD_DRAFT)])

    result = draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert result["profile"]["username"] == "KarlaBrandt"
    assert registry.updated[-1]["status"] == "completed"


def test_overlong_fields_are_clipped(registry, install_llm):
    """Der Dienst begrenzt hart: der Editor kann kein Feld anzeigen, das die
    Vertragsgrenze sprengt."""
    draft = dict(_GOOD_DRAFT)
    draft["bio"] = "b" * 900
    draft["persona"] = "p" * 5000
    draft["example_post"] = "e" * 900
    install_llm([draft])

    result = draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert len(result["profile"]["bio"]) == 500
    assert len(result["profile"]["persona"]) == 2000
    assert len(result["example_post"]["content"]) == 500


def test_an_unusable_enum_is_dropped_not_guessed(registry, install_llm):
    """Werte, die der Vertrag nicht traegt, fallen weg statt geraten zu werden —
    eine falsche Angabe waere schlimmer als eine fehlende.

    „INTX" ist der schwierige Fall: vier Buchstaben, sieht wohlgeformt aus und
    ist keiner der 16 Typen. Genau solche Werte liefert ein Modell, das die
    Liste nicht kennt. Ein Dienst, der nur auf Laenge prueft, wuerde den Wert
    durchlassen und damit den ganzen Entwurf scheitern lassen, weil
    ``PersonaSetProfile`` ihn nicht kennt.
    """
    draft = dict(_GOOD_DRAFT)
    draft["gender"] = "divers"
    draft["mbti"] = "INTX"
    draft["country"] = "Deutschland"
    install_llm([draft])

    result = draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert result["profile"]["gender"] is None
    assert result["profile"]["mbti"] is None
    # Der Laendername wird aufgelöst, nicht verworfen — das Modell weiss nur
    # nicht, dass der Vertrag ein Kuerzel traegt.
    assert result["profile"]["country"] == "DE"
    # Und der Rest des Entwurfs bleibt erhalten: ein schlechter Wert in einem
    # Feld darf nicht den ganzen Vorschlag kosten.
    assert result["profile"]["username"] == "KarlaBrandt"
    assert result["example_post"] is not None


def test_a_missing_example_post_leaves_the_preview_empty(registry, install_llm):
    """Ohne Beispielbeitrag bleibt die Vorschau leer — der Dienst erfindet keinen.
    Zwei Erfindungen uebereinander (erfundene Person, erfundener Beitrag) waere
    eine Behauptung ueber eine Figur, die es nicht gibt."""
    draft = dict(_GOOD_DRAFT)
    draft["example_post"] = ""
    install_llm([draft])

    result = draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert result["example_post"] is None
    assert result["profile"]["username"] == "KarlaBrandt"


def test_an_empty_brief_is_refused_before_the_job(registry, install_llm):
    """Ohne Brief kein Aufruf: das Modell haette nichts, woran es sich
    entlangschreiben koennte, und der Aufruf waere dekorativ."""
    install_llm([dict(_GOOD_DRAFT)])

    with pytest.raises(PersonaDraftError):
        draft_persona_entry(set_id="pset_1", brief="   ")

    assert registry.created == []
    assert _FakeLLM.instances == []


def test_the_draft_never_claims_to_be_verified(registry, install_llm):
    """Ein Entwurf ist ungeprueft. ``verified`` ist eine Tatsache ueber das
    Profil, die der Entwurf nicht herstellen kann."""
    install_llm([dict(_GOOD_DRAFT)])

    result = draft_persona_entry(set_id="pset_1", brief="Bremen")

    assert result["profile"]["verified"] is False
