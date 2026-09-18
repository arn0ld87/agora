"""Der Projekt-Vertrag muss die Ablage unveraendert lassen (PR 6).

`project.json` liegt in Bestandsinstallationen auf der Platte. Der Wechsel von
der Dataclass auf Pydantic darf an diesen Dateien nichts aendern — weder an
den Schluesseln noch an ihrer Reihenfolge, noch an der Toleranz gegenueber
Feldern, die frueheren Programmstaenden entstammen.

Die Schluesselliste steht hier als Literal und nicht als Ableitung aus dem
Modell. Eine Ableitung wuerde jede Umbenennung mitmachen und genau das nicht
mehr pruefen, wofuer der Test da ist.
"""

from __future__ import annotations

import json

import pytest

from app.contracts.project_contract import Project, ProjectStatus

# Reihenfolge und Bestand wie in der abgeloesten Dataclass-``to_dict``.
EXPECTED_KEYS = [
    'project_id',
    'name',
    'status',
    'created_at',
    'updated_at',
    'files',
    'total_text_length',
    'ontology',
    'analysis_summary',
    'graph_id',
    'graph_build_task_id',
    'simulation_requirement',
    'chunk_size',
    'chunk_overlap',
    'llm_model',
    'llm_provider',
    'llm_profile_id',
    'ai_model_ref',
    'error',
]


def _legacy_payload() -> dict:
    """Ein Datensatz, wie ihn eine Bestandsinstallation geschrieben hat."""
    return {
        'project_id': 'proj_a1b2c3d4e5f6',
        'name': 'Testprojekt',
        'status': 'graph_completed',
        'created_at': '2026-09-01T10:00:00',
        'updated_at': '2026-09-02T11:30:00',
        'files': [
            {
                'original_filename': 'quelle.pdf',
                'saved_filename': 'ab12cd34.pdf',
                'path': '/uploads/projects/proj_a1b2c3d4e5f6/files/ab12cd34.pdf',
                # ganzzahlig — die alte Annotation ``Dict[str, str]`` war falsch
                'size': 20481,
            }
        ],
        'total_text_length': 4096,
        'ontology': {'entities': ['Behoerde']},
        'analysis_summary': 'Zusammenfassung',
        'graph_id': 'graph_9',
        'graph_build_task_id': 'task_7',
        'simulation_requirement': 'Wie reagieren Anwohner?',
        'chunk_size': 500,
        'chunk_overlap': 50,
        'llm_model': 'qwen3',
        'llm_provider': {'provider': 'ollama', 'api_key_set': True},
        'llm_profile_id': 'profile_3',
        'ai_model_ref': {'connection_id': 'conn_1', 'model': 'qwen3'},
        'error': None,
    }


def test_to_dict_keys_and_order_are_unchanged():
    project = Project.from_dict(_legacy_payload())
    assert list(project.to_dict().keys()) == EXPECTED_KEYS


def test_roundtrip_leaves_a_legacy_record_byte_identical():
    payload = _legacy_payload()
    roundtripped = Project.from_dict(payload).to_dict()

    assert roundtripped == payload
    # Auch die serialisierte Form, denn das ist der Dateiinhalt.
    assert json.dumps(roundtripped, ensure_ascii=False, indent=2) == json.dumps(
        payload, ensure_ascii=False, indent=2
    )


def test_status_leaves_as_string_not_as_enum_repr():
    project = Project.from_dict(_legacy_payload())

    assert project.status is ProjectStatus.GRAPH_COMPLETED
    assert project.to_dict()['status'] == 'graph_completed'


def test_unknown_keys_from_an_older_version_are_dropped_not_rejected():
    """``extra='ignore'`` ist Absicht: so verhielt sich ``from_dict`` bisher.

    Mit ``extra='forbid'`` wuerde jedes Altprojekt, das ein inzwischen
    entferntes Feld traegt, beim Laden werfen statt sich oeffnen zu lassen.
    """
    payload = _legacy_payload()
    payload['ein_feld_das_es_nicht_mehr_gibt'] = 'Altbestand'

    project = Project.from_dict(payload)

    assert 'ein_feld_das_es_nicht_mehr_gibt' not in project.to_dict()
    assert project.project_id == 'proj_a1b2c3d4e5f6'


def test_missing_optional_fields_fall_back_to_the_previous_defaults():
    project = Project.from_dict({'project_id': 'proj_minimal'})

    assert project.name == 'Unnamed Project'
    assert project.status is ProjectStatus.CREATED
    assert project.created_at == ''
    assert project.files == []
    assert project.chunk_size == 500
    assert project.chunk_overlap == 50
    assert project.total_text_length == 0
    assert project.error is None


@pytest.mark.parametrize(
    ('field', 'expected'),
    [
        ('name', 'Unnamed Project'),
        ('created_at', ''),
        ('updated_at', ''),
        ('files', []),
        ('total_text_length', 0),
        ('chunk_size', 500),
        ('chunk_overlap', 50),
    ],
)
def test_an_explicit_null_falls_back_to_the_default_instead_of_raising(
    field, expected
):
    """``null`` in einem Pflichtfeld darf ein Projekt nicht unoeffenbar machen.

    Die abgeloeste Dataclass las mit ``data.get(feld, vorgabe)`` und
    uebernahm ein ausdrueckliches ``null`` ungeprueft. Solche Datensaetze
    koennen auf der Platte liegen. Wuerde der Vertrag daran scheitern, waere
    nicht nur das Projekt betroffen: ``list`` oeffnet jedes Verzeichnis.
    """
    payload = _legacy_payload()
    payload[field] = None

    project = Project.from_dict(payload)

    assert getattr(project, field) == expected


def test_an_explicit_null_status_falls_back_to_created():
    payload = _legacy_payload()
    payload['status'] = None

    assert Project.from_dict(payload).status is ProjectStatus.CREATED


def test_an_unknown_status_still_raises():
    """Ein Wert, den es nie gab, ist etwas anderes als ein fehlender Wert.

    ``null`` wird repariert, ein unbekannter Status nicht — sonst wuerde ein
    Tippfehler im Statusfeld still zu 'created' und der Lauf saehe aus, als
    haette er nie angefangen.

    Geprueft wird auf ``ValueError`` und nicht auf ``ValidationError``: die
    abgeloeste Dataclass warf ``ValueError`` aus dem Enum-Aufruf, und
    ``ValidationError`` erbt davon. Jeder Aufrufer, der bisher ``ValueError``
    abgefangen hat, faengt sie weiterhin.
    """
    payload = _legacy_payload()
    payload['status'] = 'voellig_neuer_status'

    with pytest.raises(ValueError):
        Project.from_dict(payload)


def test_a_record_without_project_id_raises_keyerror():
    """Ein Datensatz ohne Kennung ist keiner — und war es vorher auch nicht."""
    with pytest.raises(KeyError):
        Project.from_dict({'name': 'Ohne Kennung'})
