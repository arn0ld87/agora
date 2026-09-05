"""
Report-Contract v3 (Pydantic v2) — Pflichtabschnitt-DTOs.

11 thematische Abschnitt-DTOs + ReportV3-Container.
Vorbereitung für M11.8d (Strict-Schema-Forced-Output) und M11.8e (Quote/Evidence-Anchors).

Wording-Glossar v1 (docs/glossary.md):
  VERBOTEN: prediction, rehearsal, god's eye view, future prediction
  ERLAUBT: Simulation, Szenarienanalyse, Reaktionsmuster, Einschätzung
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provider_types import ProviderType
from .report_contract import EvidenceRecordModel, SimulationSnapshotModel


_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)

CLAIM_MIN_EVIDENCE_FOR_CLAIM: int = 1
"""ADR-0002-Floor: Ein Claim braucht mindestens ein stützendes Evidence-Item.

Ohne stützende Evidence wird die Aussage zur Hypothese. Genau eine Quelle
trägt höchstens einen ``low``-Claim; ``medium``, ``high`` und ``verified``
behalten ihre strengeren Provenance- und Confidence-Regeln.
"""


RED_TEAM_FINDINGS_LIMIT: int = 10
"""Obergrenze für ``ReportV3.red_team_findings``.

Issue #1340: Das Limit steht hier und nicht als Zahl am Feld, weil
``ReportManager._preserved_review_state()`` beim Übernehmen bestehender Befunde
dagegen prüfen muss. Zwei Zahlen an zwei Stellen driften auseinander — und die
Folge wäre, dass genau der Rebuild scheitert, den das Erben retten soll.
"""


ReportMode = Literal["strict", "balanced", "explorative"]
"""Vertrauensmodus für den Report-Output (PLAN.md §5.1, Slice P4.1).

- ``strict``: Claims ohne Evidence-Anker werden gedroppt (nicht in Hypotheses).
  Quote-Anchor-Validator hart. ``confidence_label="low"``-Claims werden gedroppt.
- ``balanced`` (Default): Phase-2-Verhalten — Hypotheses-Routing für
  Evidence-lose Claims, Low-Confidence sichtbar markiert.
- ``explorative``: alle Claims/Quotes durch, sichtbar als ``EXPLORATIVE``-Banner
  im Report-Header — für Brainstorming-/Discovery-Kontexte.
"""


DEFAULT_REPORT_MODE: ReportMode = "balanced"


class Persona(BaseModel):
    """Zielgruppen-Persona mit DACH-orientierter Demografie."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    voice_register: Literal["formal-de", "neutral-de", "technical-de", "skeptisch-de"]
    alter_range: str = Field(min_length=1, description="z. B. '35–50'")
    beruf: str = Field(min_length=1)
    region: str = Field(min_length=1, description="z. B. 'Bayern', 'DACH', 'Nordrhein-Westfalen'")
    bildungsgrad: str | None = None
    haushaltseinkommen: str | None = None
    needs: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class Segment(BaseModel):
    """Markt-/Zielgruppensegment, das mehrere Personas bündelt."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    persona_ids: list[str] = Field(default_factory=list)
    kontaktwahrscheinlichkeit_prozent: float | None = Field(
        default=None, ge=0.0, le=100.0
    )


class Claim(BaseModel):
    """Evidenz-gestützter Befund aus der Szenarienanalyse."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    statement: str = Field(min_length=8)
    evidence_refs: list[str] = Field(min_length=1, description="Pflicht: mind. 1 Evidenz-Anker")
    confidence: Literal["speculative", "low", "medium", "high", "verified"]
    persona_ids: list[str] = Field(default_factory=list)
    aggregation_basis: Literal["seed", "persona", "aggregat", "datenluecke"]
    # Issue #1160 A (Sign-off 2026-08-09): Geltungsbereich der Confidence.
    # Ein Claim, den ausschliesslich simulierte Stakeholder stuetzen, kann
    # dasselbe Label tragen wie ein quellengebundener — die Skala allein
    # unterscheidet das nicht. Das Feld macht den Unterschied im Report
    # sichtbar, ohne die Label-Semantik anzutasten (additiv, kein
    # ADR-0002-Eingriff). ``None`` = nicht erfasst, damit report-v3.json aus
    # der Zeit vor dieser Aenderung weiter validiert.
    #
    # ``empirical`` wird nie automatisch vergeben: Agora erhebt keine realen
    # empirischen Daten. Der Wert bleibt fuer manuell kuratierte Reports.
    confidence_scope: Literal["simulation_consensus", "evidence", "empirical"] | None = None
    # Issue #1012: Stufe, unter der der ``statement``-Wortlaut entstanden
    # ist. Gesetzt nur, wenn der Claim nachtraeglich abgestuft wurde —
    # dann deckt seine Formulierung eine hoehere Sicherheit ab, als das
    # Label ausweist. ``None`` heisst "nicht abgestuft", nicht "unbekannt".
    text_confidence: Literal["speculative", "low", "medium", "high", "verified"] | None = None

    @model_validator(mode="after")
    def provenance_must_not_contradict_itself(self) -> "Claim":
        """Issue #1358: Traegerschaft und Geltungsbereich beschreiben dieselbe Menge.

        Beide werden aus den stuetzenden Evidence-Items abgeleitet, also koennen
        sie nicht beliebig kombiniert werden. Vor #1358 stand in
        ``aggregation_basis`` der Literalwert ``"persona"`` — der Vertrag nahm
        jede Kombination an und der Fehler blieb sechzehn Claims lang
        unbemerkt. Diese Pruefung faengt genau die Faelle ab, die sich
        gegenseitig ausschliessen.
        """
        # ``seed_corpus`` ist eine quellengebundene Gattung. Ueberwiegt sie,
        # kann der Claim nicht ausschliesslich auf Simulationskonsens beruhen.
        if self.aggregation_basis == "seed" and self.confidence_scope == "simulation_consensus":
            raise ValueError(
                "aggregation_basis='seed' und confidence_scope='simulation_consensus' "
                "schliessen sich aus: eine Seed-getragene Aussage ist quellengebunden."
            )
        if self.aggregation_basis == "datenluecke":
            # Keine Traegerschaft heisst: kein Beleg, keine Quellenbindung und
            # erst recht kein hohes Label.
            if self.confidence_scope in {"evidence", "empirical"}:
                raise ValueError(
                    "aggregation_basis='datenluecke' vertraegt kein quellengebundenes "
                    f"confidence_scope (hier: {self.confidence_scope!r})."
                )
            if self.confidence in {"high", "verified"}:
                raise ValueError(
                    "aggregation_basis='datenluecke' vertraegt kein "
                    f"confidence={self.confidence!r}: eine Luecke traegt keinen Befund."
                )
        return self


class Multiplier(BaseModel):
    """Wachstums- oder Wirkungshebel entlang der Customer-Journey-Stufen."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kategorie: Literal["awareness", "consideration", "conversion", "retention"]
    reichweite_score: int = Field(ge=1, le=10)
    evidence_refs: list[str] = Field(default_factory=list)


class FrictionPoint(BaseModel):
    """Hindernis oder Reibungspunkt, der Adoption oder Akzeptanz verringert."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    affected_persona_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class TrustSignal(BaseModel):
    """Vertrauenssignal nach Cialdini-Kategorien (DACH-kontext)."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    signal_type: Literal[
        "social_proof",
        "authority",
        "consistency",
        "reciprocity",
        "scarcity",
        "liking",
    ]
    evidence_refs: list[str] = Field(default_factory=list)


class ChangeRecommendation(BaseModel):
    """Konkrete Handlungsempfehlung mit Priorität und Umsetzungsaufwand."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    titel: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    priority: Literal["low", "medium", "high"]
    aufwand: Literal["S", "M", "L"]
    evidence_refs: list[str] = Field(default_factory=list)


class ProjectImpact(BaseModel):
    """Einschätzung der Auswirkung des Projekts auf Segmente."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    affected_segments: list[str] = Field(default_factory=list)
    confidence: Literal["speculative", "low", "medium", "high", "verified"]
    evidence_refs: list[str] = Field(default_factory=list)


class PositioningVariant(BaseModel):
    """Positionierungs-Variante für eine spezifische Persona-Gruppe."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    titel: str = Field(min_length=1)
    claim_text: str = Field(min_length=1)
    ziel_persona_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ContentIdea(BaseModel):
    """Content-Idee mit Format-Empfehlung und Persona-Bezug."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    titel: str = Field(min_length=1)
    format: Literal["blog", "video", "podcast", "social", "whitepaper", "webinar", "other"]
    persona_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


#: Issue #1343 — Datumerkennung für Threshold-Werte.
#:
#: Der AURORA-Referenzlauf las „15. Oktober 2026“ als ``value=15.0,
#: unit="October"`` in den Bericht rutschen. Diese Muster erkennen die im
#: Seed-Material vorkommenden Schreibweisen, bevor die Number-Coercion sie
#: auseinanderreißt. Bewusst eng: nur vollständige Daten mit Jahr — ein
#: „15. Oktober“ ohne Jahr ist kein operativer Wert, sondern eine Lücke.
_DATE_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_DOT_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_DATE_PROSE_RE = re.compile(r"^(\d{1,2})\.?\s+([A-Za-zäöüÄÖÜ]+)\.?\s+(\d{4})$")

_MONTH_NUMBERS = {
    "januar": 1,
    "january": 1,
    "februar": 2,
    "february": 2,
    "märz": 3,
    "maerz": 3,
    "march": 3,
    "april": 4,
    "mai": 5,
    "may": 5,
    "juni": 6,
    "june": 6,
    "juli": 7,
    "july": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "october": 10,
    "november": 11,
    "dezember": 12,
    "december": 12,
}

#: Ein Monatsname ist keine Maßeinheit. Steht er als ``unit`` in einem
#: numerischen Threshold, war das Ursprungsdatum eine Datumsangabe, deren
#: Tag und Monat die Extraktion auseinandergerissen hat — ohne Jahr nicht
#: rekonstruierbar, also wird der Eintrag verworfen statt geraten.
_MONTH_NAMES = frozenset(_MONTH_NUMBERS)

#: Plausibilitätsgrenze für Jahreszahlen: Projektplanung spielt sich in der
#: Gegenwart ab; „0026-10-15“ oder „15202-01-01“ sind Tippfehler, keine Termine.
_MIN_YEAR = 1900
_MAX_YEAR = 2100


def parse_date_value(raw: str) -> str | None:
    """Erkennt Datumsschreibweisen und liefert ISO ``YYYY-MM-DD``, sonst None.

    Erkannt werden „15. Oktober 2026“, „15 October 2026“, „2026-10-15“ und
    „15.10.2026“ (Tag zuerst — deutschsprachiges Material). Ein String, der
    kein gültiges Kalenderdatum ergibt, liefert None und fällt der
    Number-Prüfung zu; so kann „42 Prozent“ niemals als Datum durchrutschen.
    """
    text = (raw or "").strip()
    if not text:
        return None

    year: int
    month: int
    day: int

    iso_match = _DATE_ISO_RE.match(text)
    dot_match = _DATE_DOT_RE.match(text)
    prose_match = _DATE_PROSE_RE.match(text)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
    elif dot_match:
        day, month, year = (int(part) for part in dot_match.groups())
    elif prose_match:
        day, year = int(prose_match.group(1)), int(prose_match.group(3))
        month_number = _MONTH_NUMBERS.get(prose_match.group(2).lower())
        if month_number is None:
            return None
        month = month_number
    else:
        return None

    if not (_MIN_YEAR <= year <= _MAX_YEAR):
        return None
    try:
        date(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


#: Rein numerische Strings — auch im deutschsprachigen Kommaformat. Sie sind
#: keine Daten und kein Text, sondern genau das, was ``value`` als ``float``
#: vor #1343 war.
_NUMERIC_STRING_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _numeric_string_to_float(raw: str) -> float | None:
    """Wandelt rein numerische Strings zu float, sonst None (Review PR #1379).

    Vor #1343 war ``value`` ein reines ``float``-Feld: Pydantic konvertierte
    einen numerischen String wie ``"90"`` zu ``90.0``. Mit der #1343-Erweiterung
    auf ``float | str`` wählt Smart Union für den exakten String den Textzweig,
    und die Shape-Prüfung würde denselben Payload verwerfen, den frühere
    Versionen akzeptierten. Diese Coercion stellt das frühere Verhalten her;
    alles, was nicht rein numerisch ist (echte Datumsstrings, Fließtext),
    bleibt unverändert stehen.
    """
    text = raw.strip()
    if not _NUMERIC_STRING_RE.match(text):
        return None
    return float(text.replace(",", "."))


class Threshold(BaseModel):
    """Operative Zahl oder Datum mit ausgewiesener Herkunft (Issue #1160 E).

    Zahlen wie „>90 % Traffic-Baseline“ oder „14-Tage-Rankinggrenze“ sehen im
    Fließtext alle gleich aus — egal ob sie aus dem Auftragsdokument stammen,
    aus gemessenen Daten, aus einer Norm, aus einer Betreiberentscheidung oder
    daraus, dass ein Sprachmodell sie plausibel fand. Der Leser kann sie nicht
    unterscheiden und behandelt im Zweifel alle gleich verbindlich.

    ``origin`` ist eine **eigene Dimension neben** ``EvidenceSourceKind`` und
    wird ausdrücklich nicht mit ihr vermischt: die Quellengattung beschreibt,
    woher ein *Beleg* kommt, ``origin`` beschreibt, wie eine *Zahl* zustande
    kam. Eine Vermischung würde ADR-0002 Anker 3 verwässern.

    Issue #1343: ``kind`` trennt operative Mengen (``quantity``) von
    Datumsangaben (``date``). Aus „15. Oktober 2026“ entstand sonst der
    sinnlose Eintrag ``value=15.0, unit="October"`` — ein Datum ist keine
    Menge, es trägt keine Einheit und ist in keinem Schwellwertvergleich
    verwendbar. ``kind`` ist optional mit Default ``None`` (Bestandsartefakte
    vor #1343 laden weiter; „nicht erfasst“ ist nicht dasselbe wie eine
    erfasste quantity — Muster: ``Claim.confidence_scope``). Bewusst kein
    Pydantic-Discriminated-Union: das Schema erreicht über
    ``model_json_schema()`` auch Fallback-Provider im json_object-Modus,
    wo anyOf-Unions mit zwei Objektformen unzuverlässig sind.
    """

    model_config = _STRICT

    id: str = Field(min_length=1)
    label: str = Field(
        min_length=1,
        description="Wofür die Zahl gilt, z. B. 'Traffic-Baseline' oder 'Rankinggrenze'",
    )
    #: Issue #1343: Art des Werts. quantity = operative Zahl mit Einheit,
    #: date = Kalenderdatum als ISO-Wert ('YYYY-MM-DD'). None = Altbestand
    #: vor #1343 — strukturell immer eine Zahl.
    kind: Literal["quantity", "date"] | None = Field(
        default=None,
        description=(
            "Art des Werts: quantity (operative Zahl mit unit) | date "
            "(Kalenderdatum). Datumsangaben wie '15. Oktober 2026' sind KEINE "
            "operativen Zahlen: immer kind='date' mit ISO-Wert angeben, nie "
            "als Zahl mit Monatsnamen als Einheit."
        ),
    )
    value: float | str = Field(
        description=(
            "Für quantity: der Zahlenwert selbst. Für date: das Kalenderdatum "
            "im Format 'YYYY-MM-DD' (z. B. '2026-10-15')."
        ),
    )
    unit: str | None = Field(
        default=None,
        description=(
            "Einheit der Menge, z. B. 'percent', 'days', 'eur', 'count'. "
            "Pflicht für quantity, verboten für date — ein Datum trägt keine "
            "Einheit."
        ),
    )
    purpose: Literal["alert", "target", "limit", "baseline"] = Field(
        description=(
            "Rolle der Zahl: alert (löst eine Reaktion aus) | target (angestrebt) "
            "| limit (darf nicht überschritten werden) | baseline (Ausgangswert)"
        )
    )
    origin: Literal[
        "document_requirement",
        "empirical_data",
        "external_standard",
        "operator_policy",
        "model_proposal",
        "simulation_proposal",
    ] = Field(
        description=(
            "Herkunft der Zahl. document_requirement: steht so im Auftrags- oder "
            "Seed-Dokument. empirical_data: aus gemessenen Daten abgeleitet. "
            "external_standard: aus Norm, Gesetz oder Branchenstandard. "
            "operator_policy: Festlegung des Betreibers. model_proposal: vom "
            "Sprachmodell vorgeschlagen, ohne Quelle. simulation_proposal: aus "
            "dem Verhalten der simulierten Agenten abgeleitet. Im Zweifel "
            "model_proposal — eine Zahl ohne belegbare Herkunft ist ein "
            "Vorschlag, keine Anforderung."
        )
    )
    evidence_status: Literal["verified", "derived", "heuristic"] = Field(
        default="heuristic",
        description=(
            "verified: durch eine Evidence-Referenz belegt. derived: aus belegten "
            "Werten berechnet. heuristic: plausibel, aber unbelegt."
        ),
    )
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _dates_before_numbers(cls, data: object) -> object:
        """Issue #1343: Datumsparser VOR der generischen Number-Coercion.

        Läuft, bevor Pydantic ``value`` anfasst: ein String, der eines der
        erkannten Datummuster trifft („15. Oktober 2026“, „15 October 2026“,
        „2026-10-15“, „15.10.2026“), wird zu ISO normalisiert und auf
        ``kind='date'`` festgelegt — auch gegen ein fälschlich gesetztes
        ``kind='quantity'``. Ein Datum kann so strukturell nie als Menge mit
        Monatsnamen als Einheit landen.

        Review PR #1379: Trifft der String kein Datum, aber das rein
        numerische Muster (``"90"``, ``"90,5"``), wird er zu float umgewandelt
        — so akzeptierte es ``value: float`` vor #1343 ebenfalls. Und die
        Normalisierung arbeitet auf einer flachen Kopie: Validierung ist
        beobachtungsfrei, das Eingabe-Dict bleibt unangetastet.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        raw_value = data.get("value")
        if isinstance(raw_value, str):
            iso = parse_date_value(raw_value)
            if iso is not None:
                data["value"] = iso
                if data.get("kind") != "date":
                    # Reparatur einer zerrissenen Mengenlesart: das Datum
                    # gewinnt gegen einen fälschlichen quantity-Anspruch,
                    # die mitgelieferte Einheit gehört zur Fehllesart und
                    # überlebt die Korrektur nicht. Wer dagegen ausdrücklich
                    # kind='date' deklariert und trotzdem eine Einheit
                    # mitbringt, widerspricht sich — das bleibt ein Fehler.
                    data["kind"] = "date"
                    data.pop("unit", None)
            else:
                coerced = _numeric_string_to_float(raw_value)
                if coerced is not None:
                    data["value"] = coerced
        return data

    @model_validator(mode="after")
    def verified_needs_an_evidence_ref(self) -> "Threshold":
        """``verified`` ohne Beleg wäre genau die Behauptung, die #1160 E adressiert.

        Ein Modell, das eine Zahl erfindet und sie als belegt markiert, wäre
        schlimmer als eines, das sie ehrlich als ``heuristic`` ausweist — der
        Leser verlässt sich dann auf einen Beleg, den es nicht gibt.
        """
        if self.evidence_status == "verified" and not self.evidence_refs:
            raise ValueError(
                "evidence_status='verified' verlangt mindestens eine evidence_ref."
            )
        return self

    @model_validator(mode="after")
    def kind_matches_value_shape(self) -> "Threshold":
        """Issue #1343: ``kind``, Wertform und Einheit müssen zusammenpassen.

        - ``date``: ISO-Kalenderdatum, keine Einheit.
        - ``quantity`` (oder Altbestand ohne kind): echte Zahl mit Einheit;
          ein Monatsname ist keine Einheit — der verstümmelte AURORA-Eintrag
          ``{value: 15.0, unit: "October"}`` wird hier verworfen, statt ins
          Artefakt zu rutschen.
        - Textwerte trägt ausschließlich ``date``; alles andere wäre eine
          Menge mit erfundener Form.
        """
        if self.kind == "date":
            if not isinstance(self.value, str) or not _DATE_ISO_RE.match(self.value):
                raise ValueError(
                    "kind='date' verlangt einen ISO-Datumswert ('YYYY-MM-DD')."
                )
            # Review PR #1379: Das Muster allein lässt „2026-02-30“ durch.
            # Der Vergleich gegen den Parser übernimmt dessen komplette
            # Kalender- und Jahresprüfung (1900–2100) — eine zweite,
            # abweichende Datumslogik an dieser Stelle würde garantiert
            # driften. Da der Wert ISO-geformt ist, gilt Gleichheit genau
            # dann, wenn Parser und Contract dasselbe gültige Datum sehen.
            if parse_date_value(self.value) != self.value:
                raise ValueError(
                    f"'{self.value}' ist kein gültiges Kalenderdatum "
                    f"(ISO 'YYYY-MM-DD', Jahr {_MIN_YEAR}–{_MAX_YEAR})."
                )
            if self.unit is not None:
                raise ValueError(
                    "kind='date' trägt keine Einheit — ein Datum ist keine Menge."
                )
            return self
        if isinstance(self.value, str):
            raise ValueError(
                "Nur kind='date' darf einen Textwert tragen; operative "
                "Schwellwerte sind Zahlen."
            )
        if not self.unit or not self.unit.strip():
            raise ValueError("Eine operative Zahl braucht eine Einheit (unit).")
        if self.unit.strip().lower() in _MONTH_NAMES:
            raise ValueError(
                f"'{self.unit}' ist ein Monatsname, keine Einheit — ein Datum "
                "gehört als kind='date' mit ISO-Wert ('YYYY-MM-DD') ins Feld."
            )
        return self

    @property
    def display_value(self) -> str:
        """Menschlesbare Form: „90 percent“ bzw. das ISO-Datum ohne Einheit."""
        if self.kind == "date":
            return str(self.value)
        return f"{float(self.value):g} {self.unit}"


class DataGap(BaseModel):
    """Datenlücke, die Einschätzungsqualität einschränkt."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    suggested_fixes: list[str] = Field(default_factory=list)
    #: Issue #1319: Datenlücke und Hypothese entstehen im selben Zweig aus
    #: demselben Claim. Die Beziehung gehört in den Vertrag, nicht als
    #: ``[siehe …]``-Anhängsel in die Beschreibung — nur so kann ein Consumer
    #: sie auflösen, und nur so faellt beim Rendern auf, wenn das Ziel fehlt.
    #: Traegt die exportierte Hypothesen-ID (``H<n>_<i>`` / ``HA<n>_<i>``),
    #: nicht die abschnittsinterne Rohform.
    related_hypothesis_id: str | None = None


class Hypothesis(BaseModel):
    """Hypothese ohne harte Evidence — separater Slot in ReportV3.

    Abgrenzung zu DataGap:
    - DataGap = strukturelle Datenlücke, die Einschätzungsqualität limitiert.
    - Hypothesis = inhaltliche Behauptung ohne Beleg, mit Rationale.
    """

    model_config = _STRICT

    id: str = Field(min_length=1)
    hypothesis_text: str = Field(min_length=1)
    rationale: str = ""
    suggested_evidence: list[str] = Field(default_factory=list)
    origin_section_index: int | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SimulationContribution(BaseModel):
    """Wie viel die Simulation zu den validierten Aussagen beiträgt (#1304, S3).

    Die Kritik am Referenzlauf lautete: 24 Runden Simulation, keine einzige
    validierte Aussage auf einer Agentenaktion. Ohne diese Zahl ist nach jedem
    Eingriff an Sampling oder Interviewkontext unklar, ob er gewirkt hat.

    Die drei Zähler sind ineinander geschachtelt und absichtlich getrennt
    ausgewiesen: ``claims_with_action_evidence`` allein überschätzt den Beitrag
    (ein zweiter Beleg trägt die Aussage womöglich ebenso),
    ``claims_requiring_action_evidence`` allein unterschätzt ihn.

    Die Anteile sind ``None``, solange es keine validierte Aussage gibt — eine
    0.0 würde "kein Beitrag" behaupten, wo nichts gemessen wurde.
    """

    model_config = _STRICT

    validated_claims: int = Field(default=0, ge=0)
    #: Mindestens ein stützender Beleg aus der Simulation (``agent_quote`` oder
    #: ``agent_action``) — Interviews eingeschlossen.
    claims_with_simulation_evidence: int = Field(default=0, ge=0)
    #: Mindestens ein stützender Beleg ist eine beobachtete Aktion aus Phase 3.
    claims_with_action_evidence: int = Field(default=0, ge=0)
    #: *Alle* stützenden Belege sind Aktionen — ohne die Simulationsrunden gäbe
    #: es diese Aussage nicht.
    claims_requiring_action_evidence: int = Field(default=0, ge=0)
    simulation_share: float | None = Field(default=None, ge=0.0, le=1.0)
    action_share: float | None = Field(default=None, ge=0.0, le=1.0)
    action_necessary_share: float | None = Field(default=None, ge=0.0, le=1.0)


ModelAttributionStage = Literal[
    "ontology",
    "graph_extraction",
    "simulation",
    "report_outline",
    "report_section",
    "report_synthesis",
    "red_team",
    "evidence_extraction",
    "interview",
    "other",
]
"""Slice 8 (2026-05-16): kanonische Stage-Labels für model_attribution.

Lose enumeriert — neue Pipeline-Stages können den Wert frei wählen, aber
typische Bezeichner sind festgeschrieben, damit die Frontend-Provenance-
Tabelle stabile Gruppierungen rendert.
"""


class ModelAttribution(BaseModel):
    """Welches LLM-Modell hat welche Pipeline-Stage produziert.

    Slice 8 (User-Bericht 2026-05-16): "Es hinterlegt nirgendwo welches Modell
    für welchen Teil der Erstellung zuständig war." Pro abgeschlossener Stage
    ein Eintrag — Frontend rendert sie als ausklappbare Provenance-Sektion.
    Felder absichtlich optional (außer stage/provider/model_id), damit nicht
    jeder Provider Tokens/Latency liefert.
    """

    model_config = _STRICT

    stage: ModelAttributionStage
    provider: ProviderType = Field(description="z. B. 'ollama', 'openai', 'google'")
    model_id: str = Field(min_length=1, description="Backend-Modell-ID, z. B. 'qwen2.5:32b'")
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0.0)
    started_at: datetime | None = None
    note: str | None = Field(
        default=None,
        max_length=200,
        description="Optionaler Hinweis (z. B. 'fallback nach timeout').",
    )


class ReportV3(BaseModel):
    """
    Container für alle 11 Pflichtabschnitte des strukturierten Reports v3.

    schema_version=4 ist als Literal festgelegt — verhindert Versions-Drift
    analog zu ReportContractModel(schema_version=2).
    """

    model_config = _STRICT

    schema_version: Literal[4] = 4
    report_id: str = Field(min_length=1)
    generated_at: datetime
    evidence_index: dict[str, EvidenceRecordModel] = Field(default_factory=dict)
    report_mode: ReportMode = Field(
        default=DEFAULT_REPORT_MODE,
        description="Vertrauensmodus (PLAN.md §5.1). Default 'balanced'.",
    )
    personas: list[Persona] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    multipliers: list[Multiplier] = Field(default_factory=list)
    friction_points: list[FrictionPoint] = Field(default_factory=list)
    trust_signals: list[TrustSignal] = Field(default_factory=list)
    change_recommendations: list[ChangeRecommendation] = Field(default_factory=list)
    project_impacts: list[ProjectImpact] = Field(default_factory=list)
    positioning_variants: list[PositioningVariant] = Field(default_factory=list)
    content_ideas: list[ContentIdea] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    # Issue #1160 E: operative Zahlen mit ausgewiesener Herkunft. Additiv,
    # Default leer — Bestandsreports ohne den Slot laden unveraendert.
    thresholds: list[Threshold] = Field(default_factory=list)
    # Slice 8 (2026-05-16): Modell-Provenance pro Pipeline-Stage. Default
    # leer → backward-kompatibel zu Reports vor v3.1 (alte Fixtures laden ok).
    model_attribution: list[ModelAttribution] = Field(
        default_factory=list,
        description="Welches LLM-Modell hat welche Stage produziert.",
    )
    # Issue #1192: Stand der Simulation beim Start dieser Reportgenerierung.
    # Additiv, Default None — Bestandsreports ohne den Slot laden unveraendert.
    simulation_snapshot: SimulationSnapshotModel | None = Field(
        default=None,
        description="Simulationsstand zum Startzeitpunkt des Reports.",
    )
    # Issue #1304 (S3): Wie viel die Simulation zu den validierten Aussagen
    # beitraegt. Additiv, Default None — Bestandsreports ohne den Slot laden
    # unveraendert.
    simulation_contribution: SimulationContribution | None = Field(
        default=None,
        description="Anteil der validierten Aussagen, die die Simulation traegt.",
    )
    # Slice 5 (2026-05-17): Red-Team-Findings aus echo_chamber_review-Stage.
    # RED_TEAM_FINDINGS_LIMIT begrenzt die Anzahl; leer = kein Echo-Problem erkannt.
    red_team_findings: list[str] = Field(
        default_factory=list,
        max_length=RED_TEAM_FINDINGS_LIMIT,
        description=f"Befunde der Red-Team-Review-Stage (max. {RED_TEAM_FINDINGS_LIMIT}).",
    )

    @model_validator(mode="after")
    def validate_unique_export_ids(self) -> "ReportV3":
        """Issue #1341/#1342: Claim- und Gap-IDs muessen global eindeutig sein.

        Die IDs entstehen abschnittsweise und werden anschliessend zu einer
        flachen Liste gemergt. Solange jeder Abschnitt bei 1 zu zaehlen
        beginnt, legen sich die Nummernraeume uebereinander: im Referenzlauf
        standen 10 Claims auf 8 IDs und 125 Datenluecken auf 22. Ein Consumer,
        der eine ID aufloest, bekommt dann irgendeinen der Traeger.

        Die Pruefung gehoert in den Vertrag und nicht in einen Test: ein
        Artefakt mit kollidierenden IDs ist nicht "unschoen", es ist nicht
        interpretierbar. Bestandsartefakte aus der Zeit vor der Umstellung
        koennen daran scheitern — dann liefert
        ``ReportManager.build_report_v3_markdown()`` ``None`` und protokolliert
        den Grund, statt mehrdeutige IDs weiterzureichen.
        """
        for label, collection in (("Claim", self.claims), ("DataGap", self.data_gaps)):
            seen: set[str] = set()
            duplicates: set[str] = set()
            for item in collection:
                if item.id in seen:
                    duplicates.add(item.id)
                seen.add(item.id)
            if duplicates:
                raise ValueError(
                    f"{label}-IDs sind nicht eindeutig: " + ", ".join(sorted(duplicates))
                )
        return self

    @model_validator(mode="after")
    def validate_evidence_cross_references(self) -> "ReportV3":
        known_ids = set(self.evidence_index)
        mismatched = [
            key
            for key, record in self.evidence_index.items()
            if key != record.evidence_id
        ]
        if mismatched:
            raise ValueError(
                "evidence_index-Key stimmt nicht mit evidence_id ueberein: "
                + ", ".join(sorted(mismatched))
            )

        collections = (
            self.personas,
            self.claims,
            self.multipliers,
            self.friction_points,
            self.trust_signals,
            self.change_recommendations,
            self.project_impacts,
            self.positioning_variants,
            self.content_ideas,
        )
        for collection in collections:
            for item in collection:
                unknown = sorted(set(item.evidence_refs) - known_ids)
                if unknown:
                    raise ValueError(
                        f"evidence_refs von {item.id} enthalten unbekannte Evidence: "
                        + ", ".join(unknown)
                    )
        return self
