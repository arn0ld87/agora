"""f001 (Slice `jev-budget`): ``GraphToolsService._local_search`` reicht die
run_id des bereits injizierten ``LLMClient`` an ``graph_reader.local_search``
weiter, OHNE die lazy ``self.llm``-Property zu berühren — die würde bei
fehlendem ``_llm_client`` einen vollen ``LLMClient()`` (Active-Config-Lookup,
Transport-Aufbau) nur für den Attributzugriff erzwingen. Siehe
``app/services/graph_tools.py::GraphToolsService._local_search``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.graph_tools import GraphToolsService


def _make_service(llm_client: object | None) -> GraphToolsService:
    svc = GraphToolsService.__new__(GraphToolsService)
    svc.storage = MagicMock()
    svc._llm_client = llm_client
    svc.panel_tracker = None
    return svc


class TestLocalSearchRunIdSourcing:
    def test_forwards_the_injected_llm_clients_run_id(self) -> None:
        llm_client = MagicMock()
        llm_client.run_id = "run_abc"
        svc = _make_service(llm_client)

        with patch(
            "app.services.graph_tools._reader.local_search"
        ) as local_search_mock:
            svc._local_search("g1", "query")

        local_search_mock.assert_called_once()
        assert local_search_mock.call_args.kwargs["run_id"] == "run_abc"

    def test_without_an_injected_llm_client_forwards_none_and_never_builds_one(
        self,
    ) -> None:
        svc = _make_service(None)

        with patch(
            "app.services.graph_tools._reader.local_search"
        ) as local_search_mock, patch(
            "app.services.graph_tools.LLMClient"
        ) as llm_client_cls:
            svc._local_search("g1", "query")

        local_search_mock.assert_called_once()
        assert local_search_mock.call_args.kwargs["run_id"] is None
        # Der eigentliche Punkt dieses Tests: kein lazy LLMClient() nur fuer
        # den run_id-Attributzugriff.
        llm_client_cls.assert_not_called()
