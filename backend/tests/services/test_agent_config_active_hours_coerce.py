"""Regression tests for active_hours coercion in SimulationConfigGenerator.

LLMs (z. B. gpt-5.4-nano) liefern active_hours gelegentlich als Liste von
Objekten ``[{"hour": 18, "weight": 0.8}, ...]`` statt als ``list[int]``.
Vor dem Fix landete dieser Wert ungeprüft in ``AgentActivityConfig.active_hours``
und ließ später ``_sim_common.compute_start_hour_offset`` mit
``TypeError: int() argument ... not 'dict'`` crashen.

Der Fix nutzt den bereits existierenden Helper
``SimulationConfigGenerator._coerce_int_list`` an der Aufruf-Stelle in
``_generate_agent_configs_batch``. Diese Tests sichern das Verhalten ab.
"""

from app.services.simulation_config_generator import SimulationConfigGenerator


class TestCoerceIntListActiveHours:
    """Verhalten des Helpers für die drei real auftretenden LLM-Shapes."""

    def test_pure_int_list_passes_through(self) -> None:
        result = SimulationConfigGenerator._coerce_int_list([9, 10, 11], default=[0])
        assert result == [9, 10, 11]

    def test_dict_shape_extracts_hour_key(self) -> None:
        """gpt-5.4-nano-Shape: [{"hour": 18, "weight": 0.8}, ...]."""
        llm_output = [
            {"hour": 9, "weight": 0.5},
            {"hour": 18, "weight": 0.8},
        ]
        result = SimulationConfigGenerator._coerce_int_list(llm_output, default=[0])
        assert result == [9, 18]

    def test_mixed_garbage_drops_invalid_items(self) -> None:
        """Müll-Items werden gedroppt, valide Items bleiben — kein Crash."""
        llm_output = [9, "ten", {"hour": 11}, None, {"weight": 0.5}]
        result = SimulationConfigGenerator._coerce_int_list(llm_output, default=[0])
        # 9 (int), 11 (dict mit "hour") überleben; "ten", None, dict ohne hour fallen raus.
        assert result == [9, 11]

    def test_empty_input_falls_back_to_default(self) -> None:
        """Komplett leeres/None-Input → Default-Range, nicht crashen."""
        assert SimulationConfigGenerator._coerce_int_list(None, default=[8, 9]) == [8, 9]
        assert SimulationConfigGenerator._coerce_int_list("nonsense", default=[8, 9]) == [8, 9]
