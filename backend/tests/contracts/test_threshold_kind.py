"""Issue #1343 — Datumswerte sind keine operativen Schwellwerte.

Der AURORA-Referenzlauf extrahierte aus „15. Oktober 2026" den Threshold
``{"value": 15.0, "unit": "October", "evidence_status": "heuristic"}`` —
der Tag als Zahl, der Monatsname als Einheit. Beides ist in keinem
Vergleich verwendbar: ein Datum ist kein operativer Wert, es hat keine
Einheit und keinen Sinn als Schwellwert.

Die ``kind``-Diskriminante trennt operative Zahlen (``quantity``) von
Datumsangaben (``date``). Sie ist bewusst **optional mit Default ``None``**
statt einer Discriminated Union:

- Bestandsartefakte ohne ``kind`` laden weiter — vor #1343 war ``value``
  strukturell immer eine Zahl. ``None`` heißt „nicht erfasst“, nicht
  „erfasste quantity“ (dasselbe Muster wie ``Claim.confidence_scope``,
  #1160 A).
- Das Schema geht über ``model_json_schema()`` an ``chat_json``, auch an
  Fallback-Provider im json_object-Modus (Ollama). Eine anyOf-Union mit
  zwei Objektformen ist dort unzuverlässig; ein flaches Modell bleibt
  provider-sicher.

Der Datumsparser läuft im ``mode="before"``-Validator — also bevor
Pydantic ``value`` anfasst. Genau dort ist der Eingriff gefordert: vor der
generischen Number+Unit-Coercion, nicht danach.
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from app.contracts.report_v3 import Threshold, parse_date_value


def _threshold(**overrides) -> Threshold:
    payload = {
        "id": "thr_01",
        "label": "Traffic-Baseline",
        "value": 90.0,
        "unit": "percent",
        "purpose": "baseline",
        "origin": "document_requirement",
    }
    payload.update(overrides)
    return Threshold(**payload)  # type: ignore[arg-type]


class TestKindDiscriminant:
    def test_bestandsartefakt_ohne_kind_laedt_unveraendert(self) -> None:
        """Vor #1343 gab es kein ``kind`` — alte report-v3.json bleiben gültig."""
        threshold = _threshold()

        assert threshold.kind is None
        assert threshold.value == 90.0
        assert threshold.unit == "percent"

    def test_explizites_quantity_ist_gueltig(self) -> None:
        threshold = _threshold(kind="quantity")

        assert threshold.kind == "quantity"

    def test_eine_erfundene_art_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            _threshold(kind="datum")


class TestDateRecognition:
    """Alle vier Schreibweisen aus dem Issue müssen dasselbe ISO-Datum ergeben."""

    @pytest.mark.parametrize(
        ("rohtext", "iso"),
        [
            ("15. Oktober 2026", "2026-10-15"),
            ("15 October 2026", "2026-10-15"),
            ("2026-10-15", "2026-10-15"),
            ("15.10.2026", "2026-10-15"),
        ],
    )
    def test_datumsschreibweisen_werken_zu_iso_normalisiert(
        self, rohtext: str, iso: str
    ) -> None:
        threshold = Threshold.model_validate(
            {
                "id": "production_start",
                "label": "Produktivstart",
                "value": rohtext,
                "purpose": "target",
                "origin": "document_requirement",
            }
        )

        assert threshold.kind == "date"
        assert threshold.value == iso
        assert threshold.unit is None

    def test_ein_datum_gewinnt_gegen_faelschlich_gesetztes_quantity(self) -> None:
        """„Datumswerte dürfen nicht in operative Mengen-/Threshold-Objekte
        fallen“ — auch dann nicht, wenn der Aufrufer kind='quantity' behauptet."""
        threshold = Threshold.model_validate(
            {
                "id": "production_start",
                "label": "Produktivstart",
                "value": "15. Oktober 2026",
                "kind": "quantity",
                "unit": "days",
                "purpose": "target",
                "origin": "document_requirement",
            }
        )

        assert threshold.kind == "date"
        assert threshold.value == "2026-10-15"

    def test_parser_liefert_none_fuer_kein_datum(self) -> None:
        assert parse_date_value("42 Prozent") is None
        assert parse_date_value("") is None
        assert parse_date_value("irgendein Text") is None

    def test_parser_lehnt_ungueltige_kalenderdaten_ab(self) -> None:
        assert parse_date_value("2026-02-30") is None
        assert parse_date_value("31.02.2026") is None
        assert parse_date_value("32. Januar 2026") is None
        assert parse_date_value("15. Foober 2026") is None


class TestDateStructure:
    def test_ein_datum_traegt_keine_einheit(self) -> None:
        with pytest.raises(ValidationError, match="keine Einheit"):
            Threshold.model_validate(
                {
                    "id": "production_start",
                    "label": "Produktivstart",
                    "value": "2026-10-15",
                    "kind": "date",
                    "unit": "days",
                    "purpose": "target",
                    "origin": "document_requirement",
                }
            )

    def test_kind_date_verlangt_iso_form(self) -> None:
        with pytest.raises(ValidationError):
            Threshold.model_validate(
                {
                    "id": "production_start",
                    "label": "Produktivstart",
                    "value": "nächstes Quartal",
                    "kind": "date",
                    "purpose": "target",
                    "origin": "document_requirement",
                }
            )

    def test_kind_date_mit_zahlenwert_ist_ungueltig(self) -> None:
        with pytest.raises(ValidationError):
            Threshold.model_validate(
                {
                    "id": "production_start",
                    "label": "Produktivstart",
                    "value": 15.0,
                    "kind": "date",
                    "purpose": "target",
                    "origin": "document_requirement",
                }
            )


class TestContractPathRejectsImpossibleDates:
    """Review PR #1379, Blocker 1: Am Contract-Pfad (``Threshold.model_validate``
    mit explizitem ``kind='date'``) muss dieselbe Kalenderprüfung greifen wie im
    Parser — das YYYY-MM-DD-Muster allein lässt „2026-02-30“ durch. Die
    Jahresgrenzen folgen der Parser-Plausibilität (1900–2100): Projektplanung
    spielt sich in der Gegenwart ab, „1899-12-31“ und „2101-01-01“ sind
    Tippfehler, keine Termine."""

    @pytest.mark.parametrize(
        "iso",
        ["2026-02-30", "2026-13-01", "2026-02-29"],
    )
    def test_unmoegliches_kalenderdatum_wird_am_contract_abgelehnt(
        self, iso: str
    ) -> None:
        with pytest.raises(ValidationError, match="Kalenderdatum"):
            Threshold.model_validate(
                {
                    "id": "production_start",
                    "label": "Produktivstart",
                    "value": iso,
                    "kind": "date",
                    "purpose": "target",
                    "origin": "document_requirement",
                }
            )

    @pytest.mark.parametrize("iso", ["1899-12-31", "2101-01-01"])
    def test_jahreswert_ausserhalb_der_grenzen_wird_abgelehnt(self, iso: str) -> None:
        with pytest.raises(ValidationError, match="Kalenderdatum"):
            Threshold.model_validate(
                {
                    "id": "production_start",
                    "label": "Produktivstart",
                    "value": iso,
                    "kind": "date",
                    "purpose": "target",
                    "origin": "document_requirement",
                }
            )

    def test_echter_schalttag_bleibt_gueltig(self) -> None:
        """Die Kalenderprüfung darf nicht über das Ziel hinausschießen."""
        threshold = Threshold.model_validate(
            {
                "id": "production_start",
                "label": "Produktivstart",
                "value": "2028-02-29",
                "kind": "date",
                "purpose": "target",
                "origin": "document_requirement",
            }
        )

        assert threshold.value == "2028-02-29"


class TestNumericStringCoercion:
    """Review PR #1379, Blocker 2: Vor #1343 war ``value: float`` — Pydantic
    konvertierte numerische Strings wie ``"90"`` zu ``90.0``. Mit
    ``float | str`` wählt Smart Union für den exakten String den Textzweig;
    ohne Coercion würde ein älterer bzw. providerseitig leicht abweichender
    Payload plötzlich abgelehnt. Die Coercion stellt das frühere Verhalten
    her — echte Datumsstrings bleiben Strings."""

    @pytest.mark.parametrize(
        ("rohtext", "erwartet"),
        [("90", 90.0), ("-3", -3.0), ("12.5", 12.5), ("90,5", 90.5)],
    )
    def test_numerischer_string_wird_zu_float_wie_vor_1343(
        self, rohtext: str, erwartet: float
    ) -> None:
        threshold = _threshold(value=rohtext)

        assert isinstance(threshold.value, float)
        assert threshold.value == erwartet
        assert threshold.unit == "percent"

    def test_datumsstring_bliebt_string_und_wird_zu_date(self) -> None:
        threshold = Threshold.model_validate(
            {
                "id": "production_start",
                "label": "Produktivstart",
                "value": "2026-10-15",
                "purpose": "target",
                "origin": "document_requirement",
            }
        )

        assert isinstance(threshold.value, str)
        assert threshold.value == "2026-10-15"
        assert threshold.kind == "date"

    def test_nicht_numerischer_text_bliebt_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            _threshold(value="42 Prozent")


class TestBeforeValidatorWithoutSideEffects:
    """Review PR #1379, Qualität A: Validierung darf das Eingabe-Dict nicht
    verändern — der Aufrufer behält seine Daten, auch wenn der Vertrag sie
    intern normalisiert."""

    def test_input_dict_bleibt_unveraendert(self) -> None:
        payload = {
            "id": "production_start",
            "label": "Produktivstart",
            "value": "15. Oktober 2026",
            "unit": "days",
            "purpose": "target",
            "origin": "document_requirement",
        }
        snapshot = copy.deepcopy(payload)

        Threshold.model_validate(payload)

        assert payload == snapshot


class TestQuantityStaysNumeric:
    """Negativfall: echte Mengen bleiben numerische Schwellwerte."""

    def test_normale_zahl_bliebt_numerisch(self) -> None:
        threshold = _threshold(value=42.0, unit="percent")

        assert isinstance(threshold.value, float)
        assert threshold.value == 42.0

    def test_textwert_ohne_datumform_ist_abgelehnt(self) -> None:
        """Ein String, der kein Datum ist, kann nicht als Menge durchrutschen."""
        with pytest.raises(ValidationError):
            _threshold(value="42 Prozent")

    def test_menge_braucht_einheit(self) -> None:
        with pytest.raises(ValidationError, match="Einheit"):
            _threshold(unit=None)

    @pytest.mark.parametrize(
        "monatsname",
        ["October", "Oktober", "May", "Mai", "December", "Dezember"],
    )
    def test_monatsname_ist_keine_einheit(self, monatsname: str) -> None:
        """Das verstümmelte Artefakt aus #1343 darf das Berichtsartefakt
        nicht mehr erreichen: {value: 15.0, unit: 'October'} wird verworfen."""
        with pytest.raises(ValidationError, match="Monatsname"):
            _threshold(value=15.0, unit=monatsname)


class TestDisplayValue:
    def test_menge_mit_einheit(self) -> None:
        assert _threshold(value=90.0, unit="percent").display_value == "90 percent"

    def test_datum_ohne_einheit(self) -> None:
        threshold = Threshold.model_validate(
            {
                "id": "production_start",
                "label": "Produktivstart",
                "value": "15. Oktober 2026",
                "purpose": "target",
                "origin": "document_requirement",
            }
        )

        assert threshold.display_value == "2026-10-15"


class TestSchemaReachesTheModel:
    def test_die_kind_anleitung_erreicht_das_modell(self) -> None:
        """Wie bei #1160 E geht die Anweisung über die Feldbeschreibungen ins
        JSON-Schema — der Prompt-Block bleibt unberührt (ADR-0002 Anker 1)."""
        from app.services.report_agent.schemas import SectionMetadata

        rendered = str(SectionMetadata.model_json_schema())

        assert '"date"' in rendered or "'date'" in rendered
        assert "YYYY-MM-DD" in rendered
