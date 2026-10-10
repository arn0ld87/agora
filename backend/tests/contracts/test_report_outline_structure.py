"""Issue #1832: Gliederungsstruktur ohne vordefinierte Überschriften."""
import pytest
from pydantic import ValidationError

from app.contracts.report_contract import ReportOutlineModel


def _outline(titles):
    return ReportOutlineModel(
        title="Geburtshilfe", summary="Versorgung im Landkreis",
        sections=[{"title": title, "description": "Quellenlage prüfen"} for title in titles],
    )


def test_fifteen_distinct_scenario_sections_are_valid():
    outline = _outline([f"Versorgungsfrage {i}" for i in range(15)])
    assert len(outline.sections) == 15


@pytest.mark.parametrize("titles", [[], [f"Thema {i}" for i in range(16)]])
def test_section_count_is_bounded(titles):
    with pytest.raises(ValidationError, match="sections"):
        _outline(titles)


@pytest.mark.parametrize("title", ["", "  ", "\t\n"])
def test_blank_section_title_is_invalid(title):
    with pytest.raises(ValidationError, match="title"):
        _outline([title])


@pytest.mark.parametrize("titles", [
    ["Hebammen", "HEBAMMEN"],
    ["Rettungswege bei Nacht", " Rettungswege  bei\tNacht "],
    ["Straße", "STRASSE"],
])
def test_duplicate_normalized_titles_are_invalid(titles):
    with pytest.raises(ValidationError, match="doppelt|eindeutig"):
        _outline(titles)


def test_title_is_trimmed_without_changing_its_meaning():
    outline = _outline(["  Versorgung bei Nacht  "])
    assert outline.sections[0].title == "Versorgung bei Nacht"
