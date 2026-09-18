"""Projekt-Contract (Pydantic v2) — PR 6, docs/plans/supabase.md §11.

Ein Projekt ist der Implementierungsbegriff fuer die Ablage eines Laufs:
Metadaten in ``uploads/projects/<project_id>/project.json``, Artefakte im
selben Verzeichnis. Dieser Vertrag beschreibt ausschliesslich die Metadaten.

Bis hierher war ``Project`` eine Dataclass, deren ``to_dict()`` ueber drei
Endpunkte ausgeliefert wird (``GET /project/<id>``, ``GET /project/list``,
``POST /project/<id>/reset``). Damit lag eine Dataclass auf einer API-Grenze,
was contracts-first ausschliesst. Der Vertrag loest das, ohne die Ablage zu
veraendern: ``to_dict`` und ``from_dict`` erhalten Schluessel, Reihenfolge und
Werte bestehender ``project.json``-Dateien.

Diese Zusage gilt fuer **formgerechte** Datensaetze. Wo ein Feld den falschen
Typ traegt, ist sie ausdruecklich nicht zu halten, und zwei Faelle sind
dokumentiert statt stillschweigend hingenommen: ein ausdrueckliches ``null``
in einem Pflichtfeld wird auf den Vorgabewert zurueckgesetzt (siehe
``_tolerate_null_in_required_fields``), und Pydantic wandelt im Normalmodus
einen Zahlenstring in eine Zahl — aus ``"chunk_size": "500"`` wird beim
naechsten Speichern ``500``. Beides betrifft nur Datensaetze, die vorher schon
von der Form abwichen; der Inhalt bleibt in beiden Faellen erhalten.

Zwei Entscheidungen sind hier bewusst getroffen und keine Nachlaessigkeit:

``extra="ignore"`` statt ``extra="forbid"``. Die uebrigen Vertraege dieses
Verzeichnisses verbieten Zusatzfelder, weil sie Requests von aussen
beschreiben. Dieser Vertrag liest zusaetzlich Dateien, die frueheren
Programmstaenden entstammen. Das bisherige ``from_dict`` hat unbekannte
Schluessel stillschweigend verworfen; ``forbid`` wuerde aus jedem Altprojekt
mit einem abgelegten Zusatzfeld einen Ladefehler machen. Der Vertrag bildet
hier den Bestand ab, nicht den Wunsch.

``files`` ist ``list[dict[str, Any]]`` und kein eigenes Teilmodell. Der
Eintrag, den ``save_file_to_project`` erzeugt, traegt ``original_filename``,
``saved_filename``, ``path`` und ein ganzzahliges ``size`` — die alte
Annotation ``List[Dict[str, str]]`` war schon falsch. Ein striktes Teilmodell
wuerde Altprojekte mit abweichender Form beim Laden abweisen. Die Form der
Eintraege zu haerten ist eine eigene Aufgabe, keine Nebenwirkung dieser.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectStatus(str, Enum):
    """Status eines Projekts.

    Kanonisch hier, nicht in ``app/models/project.py``: der Status steht im
    Vertrag und wird von dort re-exportiert. Die Reihenfolge und die Werte
    sind unveraendert — sie stehen so in jeder bestehenden ``project.json``.
    """

    CREATED = 'created'
    ONTOLOGY_GENERATED = 'ontology_generated'
    GRAPH_BUILDING = 'graph_building'
    GRAPH_COMPLETED = 'graph_completed'
    # Issue B2 („Abbrechen & Pause"): kooperativer Abbruch eines graph_build.
    # Kein FAILED — der Graph traegt bereits committete Episoden, Entities und
    # Relations und bleibt auswertbar, nur unvollstaendig gegenueber dem
    # Ursprungsdokument.
    GRAPH_INCOMPLETE = 'graph_incomplete'
    FAILED = 'failed'


class Project(BaseModel):
    """Metadaten eines Projekts.

    ``created_at`` und ``updated_at`` sind ISO-8601-Zeichenketten und keine
    ``datetime``: so stehen sie in der Ablage, und ``list_projects`` sortiert
    lexikografisch darueber. Eine Umstellung auf ``datetime`` aendert das
    Format in der Datei und gehoert zur PostgreSQL-Tabelle, nicht hierher.
    """

    model_config = ConfigDict(extra='ignore', use_enum_values=False)

    project_id: str = Field(..., min_length=1)
    name: str = 'Unnamed Project'
    status: ProjectStatus = ProjectStatus.CREATED
    created_at: str = ''
    updated_at: str = ''

    # Artefaktverweise: je Eintrag original_filename, saved_filename, path, size.
    files: list[dict[str, Any]] = Field(default_factory=list)
    total_text_length: int = 0

    # Ontologie (gefuellt, nachdem Oberflaeche 1 sie erzeugt hat)
    ontology: Optional[dict[str, Any]] = None
    analysis_summary: Optional[str] = None

    # Graph (gefuellt, nachdem Oberflaeche 2 durchgelaufen ist)
    graph_id: Optional[str] = None
    graph_build_task_id: Optional[str] = None

    # Konfiguration des Laufs
    simulation_requirement: Optional[str] = None
    chunk_size: int = 500
    chunk_overlap: int = 50

    # LLM-Auswahl, die der Benutzer im Frontend fuer diesen Projektlauf
    # getroffen hat. ``llm_provider`` traegt **keine** Secrets — abgelegt wird
    # nur ``redacted_metadata()`` (Provider, Base-URL, api_key_set). Der
    # API-Key bleibt session-local bzw. im Fernet-Store.
    llm_model: Optional[str] = None
    llm_provider: Optional[dict[str, Any]] = None
    # ID des persistierten LLM-Profils, das beim Ontology-Generate aktiv war.
    llm_profile_id: Optional[str] = None
    # Kanonische (Provider-Connection, Modell)-Referenz des Ontology-Generate-
    # Laufs (``AiModelRef.model_dump()``). Auf diesem Pfad bleiben
    # ``llm_model``/``llm_provider``/``llm_profile_id`` bewusst leer — ohne das
    # Feld verloere ein wiederaufgenommener Graph-Build jede Modellbindung.
    # Traegt keine Secrets: die Connection wird nur per ID referenziert.
    ai_model_ref: Optional[dict[str, Any]] = None

    error: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def _tolerate_null_in_required_fields(cls, data: Any) -> Any:
        """Ersetzt ``null`` in Pflichtfeldern durch den Vorgabewert.

        Die abgeloeste Dataclass las mit ``data.get(feld, vorgabe)``. Steht in
        der Datei ein ausdrueckliches ``null``, liefert ``get`` nicht die
        Vorgabe, sondern ``None`` — die Dataclass uebernahm das ungeprueft und
        schrieb es beim naechsten Speichern zurueck. Es kann also
        ``project.json``-Dateien mit ``"files": null`` oder ``"name": null``
        geben.

        Pydantic wuerde daran scheitern, und der Schaden waere nicht lokal:
        ``list`` oeffnet jedes Projektverzeichnis, ein einziger solcher
        Datensatz haette damit die gesamte Projektliste unbrauchbar gemacht,
        nicht nur das betroffene Projekt.

        Das ist die einzige Stelle, an der dieser Vertrag bewusst NICHT
        zeichengleich zur Ablage ist: aus einem ``null`` wird beim naechsten
        Speichern der Vorgabewert. Betroffen sind nur Datensaetze, die vorher
        schon kaputt waren, und der Vorgabewert ist genau das, was die alte
        ``from_dict`` fuer ein fehlendes Feld eingesetzt haette.
        """
        if not isinstance(data, dict):
            return data

        defaults: dict[str, Any] = {
            'name': 'Unnamed Project',
            'status': ProjectStatus.CREATED,
            'created_at': '',
            'updated_at': '',
            'files': [],
            'total_text_length': 0,
            'chunk_size': 500,
            'chunk_overlap': 50,
        }

        repaired = {
            key: (defaults[key] if key in defaults and value is None else value)
            for key, value in data.items()
        }
        return repaired

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert fuer ``project.json`` und fuer die API.

        Ausdruecklich handgeschrieben statt ``model_dump()``: die Schluessel
        und ihre Reihenfolge sind der Dateiinhalt, den Bestandsinstallationen
        auf der Platte haben, und ``status`` muss als Zeichenkette
        herauskommen. Ein ``model_dump()`` wuerde beides an den Vertrag koppeln
        und bei jeder Feldumbenennung stillschweigend die Ablage aendern.
        """
        return {
            'project_id': self.project_id,
            'name': self.name,
            'status': (
                self.status.value
                if isinstance(self.status, ProjectStatus)
                else self.status
            ),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'files': self.files,
            'total_text_length': self.total_text_length,
            'ontology': self.ontology,
            'analysis_summary': self.analysis_summary,
            'graph_id': self.graph_id,
            'graph_build_task_id': self.graph_build_task_id,
            'simulation_requirement': self.simulation_requirement,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'llm_model': self.llm_model,
            'llm_provider': self.llm_provider,
            'llm_profile_id': self.llm_profile_id,
            'ai_model_ref': self.ai_model_ref,
            'error': self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Project':
        """Liest einen Datensatz aus der Ablage.

        ``project_id`` ist Pflicht und wirft bei Abwesenheit — ein Datensatz
        ohne Kennung ist keiner. Alle uebrigen Felder fallen auf ihre
        Vorgabewerte zurueck, unbekannte Schluessel werden verworfen. Beides
        entspricht dem Verhalten vor diesem Vertrag.
        """
        # Der Zugriff steht hier allein wegen seiner Nebenwirkung: er wirft
        # ``KeyError`` wie die abgeloeste ``from_dict``, statt den Fall als
        # ``ValidationError`` unter die uebrigen Feldfehler zu mischen.
        _ = data['project_id']
        return cls.model_validate(data)


class ProjectListResponse(BaseModel):
    """Antwortform von ``GET /project/list``."""

    model_config = ConfigDict(extra='forbid')

    projects: list[Project]
