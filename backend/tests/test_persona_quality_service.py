"""Service-level tests for the Slice 2.2 persona quality heuristics."""

from __future__ import annotations

from app.services.artifact_store import InMemoryArtifactStore
from app.services.persona_quality_service import (
    PersonaQualityService,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)

SIM_ID = "sim_abcdef012345"


def _store(profiles):
    store = InMemoryArtifactStore()
    store.write_json(SIM_ID, "reddit_profiles", profiles)
    return store


def _persona(report, username):
    for entry in report["personas"]:
        if entry["username"] == username:
            return entry
    raise AssertionError(f"persona {username!r} missing from report")


def _codes(issues):
    return {issue["code"] for issue in issues}


def test_evaluate_empty_simulation_flags_no_personas():
    service = PersonaQualityService(InMemoryArtifactStore())
    report = service.evaluate(SIM_ID)

    assert report["personas"] == []
    assert report["summary"]["total"] == 0
    assert "no_personas" in _codes(report["global_issues"])


def test_evaluate_flags_duplicate_username_as_error():
    store = _store([
        {"username": "alice", "name": "Alice A.", "bio": "x", "persona": "y", "profession": "ops"},
        {"username": "alice", "name": "Alice B.", "bio": "x", "persona": "y", "profession": "qa"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)

    for entry in report["personas"]:
        assert any(
            issue["code"] == "duplicate_username" and issue["severity"] == SEVERITY_ERROR
            for issue in entry["issues"]
        )


def test_evaluate_flags_duplicate_name_as_warning():
    store = _store([
        {"username": "a", "name": "Same", "bio": "x", "persona": "y", "profession": "ops",
         "source_entity_uuid": "u-1"},
        {"username": "b", "name": "same", "bio": "x", "persona": "y", "profession": "qa",
         "source_entity_uuid": "u-2"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)

    for entry in report["personas"]:
        codes = _codes(entry["issues"])
        assert "duplicate_name" in codes
        assert "duplicate_username" not in codes


def test_evaluate_missing_one_core_field_is_warning():
    store = _store([
        {"username": "alice", "name": "Alice", "persona": "p", "profession": "ops",
         "source_entity_uuid": "u-1"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    issue = next(
        i for i in _persona(report, "alice")["issues"]
        if i["code"] == "missing_core_fields"
    )
    assert issue["severity"] == SEVERITY_WARNING
    assert issue["detail"]["missing"] == ["bio"]


def test_evaluate_missing_all_core_fields_is_error():
    store = _store([{"username": "alice", "name": "Alice", "source_entity_uuid": "u-1"}])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    issue = next(
        i for i in _persona(report, "alice")["issues"]
        if i["code"] == "missing_core_fields"
    )
    assert issue["severity"] == SEVERITY_ERROR
    assert set(issue["detail"]["missing"]) == {"bio", "persona", "profession"}


def test_evaluate_missing_entity_link_only_for_generated_personas():
    store = _store([
        {"username": "alice", "bio": "b", "persona": "p", "profession": "ops"},
        {"username": "bob", "bio": "b", "persona": "p", "profession": "ops",
         "is_manual": True},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)

    assert "missing_entity_link" in _codes(_persona(report, "alice")["issues"])
    assert "missing_entity_link" not in _codes(_persona(report, "bob")["issues"])


def test_summary_counts_review_status_and_diversity():
    store = _store([
        {"username": "alice", "bio": "b", "persona": "p", "profession": "ops",
         "mbti": "INTJ", "source_entity_uuid": "u-1", "review_status": "approved"},
        {"username": "bob", "bio": "b", "persona": "p", "profession": "ops",
         "mbti": "INTJ", "source_entity_uuid": "u-2", "review_status": "pending"},
        {"username": "cara", "bio": "b", "persona": "p", "profession": "qa",
         "mbti": "ENFP", "source_entity_uuid": "u-3", "review_status": "rejected"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    summary = report["summary"]

    assert summary["total"] == 3
    assert summary["approved"] == 1
    assert summary["pending"] == 1
    assert summary["rejected"] == 1
    assert summary["distinct_roles"] == ["ops", "qa"]
    assert summary["distinct_mbti"] == ["enfp", "intj"]
    # role diversity = 2/3 → no warning, no info
    assert "role_diversity" not in _codes(report["global_issues"])


def test_global_role_diversity_warning_when_only_one_role():
    store = _store([
        {"username": "a", "bio": "b", "persona": "p", "profession": "ops",
         "mbti": "INTJ", "source_entity_uuid": "u-1"},
        {"username": "b", "bio": "b", "persona": "p", "profession": "ops",
         "mbti": "ENFP", "source_entity_uuid": "u-2"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    issue = next(i for i in report["global_issues"] if i["code"] == "role_diversity")
    assert issue["severity"] == SEVERITY_WARNING


def test_global_mbti_diversity_warning_when_only_one_value():
    store = _store([
        {"username": "a", "bio": "b", "persona": "p", "profession": "ops",
         "mbti": "INTJ", "source_entity_uuid": "u-1"},
        {"username": "b", "bio": "b", "persona": "p", "profession": "qa",
         "mbti": "INTJ", "source_entity_uuid": "u-2"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    issue = next(i for i in report["global_issues"] if i["code"] == "mbti_diversity")
    assert issue["severity"] == SEVERITY_WARNING


def test_role_diversity_info_severity_below_threshold():
    # 6 personas, 2 distinct roles → ratio 2/6 ≈ 0.33 < 0.34 → info severity.
    store = _store([
        {"username": f"u{i}", "bio": "b", "persona": "p",
         "profession": ("ops" if i < 5 else "qa"),
         "source_entity_uuid": f"u-{i}"}
        for i in range(6)
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    issue = next(i for i in report["global_issues"] if i["code"] == "role_diversity")
    assert issue["severity"] == SEVERITY_INFO


def test_group_entity_profession_excluded_from_core_fields():
    store = _store([
        {"username": "germany", "name": "Germany", "bio": "b", "persona": "p",
         "source_entity_uuid": "u-1", "source_entity_type": "Country"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    codes = _codes(_persona(report, "germany")["issues"])
    assert "missing_core_fields" not in codes


def test_group_entity_missing_all_remaining_core_fields_is_error():
    store = _store([
        {"username": "ngo_x", "name": "NGO X",
         "source_entity_uuid": "u-1", "source_entity_type": "NGO"},
    ])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    issue = next(
        i for i in _persona(report, "ngo_x")["issues"]
        if i["code"] == "missing_core_fields"
    )
    assert issue["severity"] == SEVERITY_ERROR
    assert set(issue["detail"]["missing"]) == {"bio", "persona"}


def test_review_status_normalised_in_persona_entries():
    store = _store([{"username": "alice", "bio": "b", "persona": "p",
                     "profession": "ops", "source_entity_uuid": "u-1"}])
    report = PersonaQualityService(store).evaluate(SIM_ID)
    assert _persona(report, "alice")["review_status"] == "pending"
