"""Issue #999 — Interview-Gate prüft Direktpfad statt nur IPC-Liveness.

Regression: ``SimulationRunner.check_env_alive()`` ist für jede abgeschlossene
Simulation ``False`` (Normalzustand nach PR #997 — die Simulation, für die ein
Report erzeugt wird, läuft nicht mehr). Der alte Early-Check in
``GraphToolsService.interview_agents()`` brach deshalb bei JEDEM Report-Lauf
mit einem terminalen Soft-Fail ab, obwohl
``interview_client.interview_agents_batch`` selbst schon automatisch auf den
funktionierenden Direktpfad (``interview_agents_batch_direct``) umschaltet,
sobald die IPC-Umgebung tot ist. Der Direktpfad war für den ReportAgent damit
toter Code.

Dieser Test belegt: bei toter IPC-Umgebung, aber verfügbarem Direktpfad
(persistierte Personas), muss ``SimulationRunner.interview_agents_batch``
tatsächlich aufgerufen werden statt eines sofortigen Soft-Fails.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.sim import interview_direct

# Persistierte Personas — genau das, was den Direktpfad verfügbar macht.
PERSISTED_PERSONAS = [
    {
        "user_id": 1,
        "username": "anna_m",
        "name": "Anna Musterfrau",
        "bio": "Konsumentin, interessiert an Nachhaltigkeit.",
        "profession": "Konsumentin",
    }
]


def _store_with_personas() -> MagicMock:
    """Artifact-Store-Doppel, über das ``direct_interviews_available`` echt läuft.

    Bewusst KEIN Patch auf ``direct_interviews_available`` selbst: dieses Symbol
    wird erst durch den Fix nach ``interview_client`` importiert. Ein Patch
    darauf würde den Test auf dem Vor-Fix-Stand schon im Mock-Setup mit einem
    ``AttributeError`` abbrechen lassen — also aus dem falschen Grund rot sein
    und den eigentlichen Defekt gar nicht prüfen. ``_store`` dagegen existiert
    auf beiden Ständen, sodass der Unterschied allein im Produktivverhalten
    liegt.
    """
    store = MagicMock()
    store.read_json.side_effect = lambda simulation_id, name, default=None: (
        PERSISTED_PERSONAS if name == "reddit_profiles" else default
    )
    return store


class TestInterviewUsesDirectPathWhenEnvDead:
    def _make_service(self):
        from app.services.graph_tools import GraphToolsService

        svc = GraphToolsService.__new__(GraphToolsService)
        svc._llm_client = MagicMock()
        # Eine Antwort deckt beide chat_json-Aufrufe ab (Selection + Fragen-
        # Generierung) — jeder Aufrufer liest nur die für ihn relevanten Keys.
        svc._llm_client.chat_json.return_value = {
            "selected_indices": [0],
            "reasoning": "Testauswahl",
            "questions": ["Wie bewerten Sie das neue Angebot?"],
        }
        svc._llm_client.chat.return_value = "Zusammenfassung der Interviews."
        svc._load_agent_profiles = MagicMock(
            return_value=[
                {
                    "realname": "Anna Musterfrau",
                    "username": "anna_m",
                    "bio": "Konsumentin, interessiert an Nachhaltigkeit.",
                    "profession": "Konsumentin",
                }
            ]
        )
        return svc

    def test_interview_agents_batch_called_when_env_dead_but_direct_path_available(self):
        svc = self._make_service()

        api_success = {
            "success": True,
            "interviews_count": 1,
            "result": {
                "results": {
                    "twitter_0": {
                        "response": (
                            "Ich finde das Angebot insgesamt überzeugend und "
                            "würde es weiterempfehlen."
                        )
                    },
                    "reddit_0": {
                        "response": (
                            "Der Preis ist fair, aber die Lieferzeit könnte "
                            "kürzer sein."
                        )
                    },
                }
            },
            "timestamp": "2026-08-02T00:00:00Z",
        }

        # Die IPC-Umgebung ist tot — der Normalzustand jeder abgeschlossenen
        # Simulation. Beide Aufrufwege des Liveness-Checks werden abgedeckt:
        # der alte Pfad ueber die Classmethod und der Modulpfad, den
        # interviews_possible nutzt.
        with patch(
            "app.services.simulation_runner.SimulationRunner.check_env_alive",
            return_value=False,
        ), patch(
            "app.services.sim.interview_client.check_env_alive",
            return_value=False,
        ), patch.object(
            interview_direct, "_store", return_value=_store_with_personas()
        ), patch(
            "app.services.simulation_runner.SimulationRunner.interview_agents_batch",
            return_value=api_success,
        ) as mock_batch:
            result = svc.interview_agents(
                simulation_id="sim_regression_999_finished",
                interview_requirement="Wie bewerten Sie das neue Angebot?",
                simulation_requirement="Kontext",
                max_agents=5,
            )

        mock_batch.assert_called_once()
        assert result.interviewed_count > 0, (
            f"Direktpfad haette Interviews liefern muessen, bekommen: {result!r}"
        )
        assert "Do NOT call interview_agents again" not in result.summary, (
            f"Soft-Fail haette nicht greifen duerfen, bekommen: {result.summary!r}"
        )
