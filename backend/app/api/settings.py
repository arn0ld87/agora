"""Settings API (Issue #133, SUB1 + SUB2).

Liefert das deklarative Settings-Schema, die aktuellen je Quelle
markierten Werte und nimmt Updates über zwei klar getrennte
PUT-Endpunkte entgegen.

Endpunkte (alle hinter dem Standard-Blueprint-Guard, d. h.
``AGORA_AUTH_TOKEN`` Pflicht außerhalb von ``FLASK_DEBUG=true``):

  - ``GET  /api/settings``         — alle Felder gruppiert nach Sektion
  - ``GET  /api/settings/schema``  — nur Meta (Typ, Default, Enum, Flags)
  - ``PUT  /api/settings``         — non-secret Felder bulk-aktualisieren
  - ``PUT  /api/settings/secrets`` — Secret-Felder mit ``confirm: true``
                                     in einer separaten Maske setzen

Begründung für die Trennung Schema ↔ Werte: das Frontend lädt einmal
das Schema (cachebar), pollt dann nur die Werte; das spart bei großen
Settings-Listen Bandbreite und macht den Schema-Cache im Store
testbar.

Begründung für die Trennung PUT ↔ PUT/secrets: Secrets verlangen ein
explizites Bestätigungs-Flag (Self-Lockout-Schutz für
``AGORA_AUTH_TOKEN``) und dürfen nie gemeinsam mit harmlosen
Edit-Massenoperationen passieren. Der Body-Validator weist Secrets
auf dem regulären Endpunkt aktiv zurück.
"""

from __future__ import annotations

from flask import Blueprint, request

from ..services.settings_layer import get_default_service
from ..services.settings_schema import SECTIONS, field_by_key
from ..services.settings_event_bus import publish_settings_changed
from ..services.settings_validator import validate_payload
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger


settings_bp = Blueprint('settings', __name__)
logger = get_logger('agora.api.settings')


@settings_bp.route('', methods=['GET'])
@settings_bp.route('/', methods=['GET'])
@handle_api_errors
def get_settings():
    """Liefert alle Felder, gruppiert nach Sektion.

    Response-Schema (vereinfacht):

        {
          "success": true,
          "data": {
            "sections": ["llm", "neo4j", ...],
            "fields": {
              "llm": [
                 {"key": "LLM_MODEL_NAME", "type": "string",
                  "value": "qwen2.5:32b", "default": "qwen2.5:32b",
                  "source": "env", "is_set": true,
                  "secret": false, "reload_required": false},
                 ...
              ],
              ...
            }
          }
        }

    Secrets-Felder werden durchgehend mit ``value: null`` und
    ``is_set: bool`` ausgeliefert — Klartext-Secret-Leakage wäre auch
    in der GET-Antwort ein Layering-Bruch (Issue-Akzeptanz).
    """
    service = get_default_service()
    return json_success({
        'sections': list(SECTIONS),
        'fields': service.get_all_grouped(),
    })


@settings_bp.route('/schema', methods=['GET'])
@settings_bp.route('/schema/', methods=['GET'])
@handle_api_errors
def get_settings_schema():
    """Reine Schema-Beschreibung ohne aktuelle Werte. Defaults sind
    enthalten, bei Secrets aber maskiert (``default: null``).
    """
    service = get_default_service()
    return json_success({
        'sections': list(SECTIONS),
        'fields': service.get_schema(),
    })


def _payload_dict_or_none() -> dict | None:
    """Body als JSON-Object oder ``None``, wenn das Parsing scheitert.

    Wir benutzen ``silent=True``, damit ein leerer Body kein 500 wirft;
    die Validierung lehnt nicht-Dict-Bodies anschließend mit einem
    klaren ``invalid_payload``-Error ab.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return None
    return payload


@settings_bp.route('', methods=['PUT'])
@settings_bp.route('/', methods=['PUT'])
@handle_api_errors
def put_settings():
    """Bulk-Update für non-secret Felder.

    Body-Form: flach ``{key: value}``. Secrets werden vom Validator
    abgelehnt (``code='secret_not_allowed'``). Bei Validation-Errors
    wird **nichts** persistiert (all-or-nothing) und HTTP 400
    zurückgegeben — die Errors-Liste enthält alle Felder, damit das
    Frontend mehrere Inline-Hints gleichzeitig zeigen kann.

    Erfolgreiches Update schreibt atomar nach
    ``backend/instance/settings.json``. Antwort enthält das aktuelle
    Sektions-Bild (gleiche Form wie GET), damit das Frontend den
    Source-Status nach dem Save direkt rendern kann ohne extra
    Round-Trip.
    """
    raw_payload = _payload_dict_or_none()
    if raw_payload is None or not isinstance(raw_payload, dict):
        return json_error(
            'invalid_payload', status=400, code='invalid_payload',
            message='PUT-Body muss ein JSON-Object sein.',
        )

    service = get_default_service()
    validated, errors = validate_payload(
        raw_payload,
        allow_secrets=False,
        effective_settings=service.effective_snapshot(),
    )
    if errors:
        return _validation_error_response(errors)

    service.apply_payload(validated, persist=True)
    _publish_settings_changed(validated.keys(), source='settings')
    return json_success({
        'sections': list(SECTIONS),
        'fields': service.get_all_grouped(),
        'updated_keys': sorted(validated.keys()),
    })


@settings_bp.route('/secrets', methods=['PUT'])
@settings_bp.route('/secrets/', methods=['PUT'])
@handle_api_errors
def put_settings_secrets():
    """Sondermaske: setzt ausschließlich Secret-Felder.

    Body-Form: ``{"confirm": true, "fields": {KEY: value, ...}}``.
    ``confirm`` ist ein simpler Self-Lockout-Schutz — das Frontend
    zwingt die Operatorin, nochmal aktiv zu bestätigen, bevor ein
    versehentlich gesetzter ``AGORA_AUTH_TOKEN`` den eigenen Zugang
    sperrt. Der Endpoint validiert nur die Felder als Secrets-only;
    weitergehende Self-Lockout-Strategien (Verify per altem Token)
    bleiben Aufgabe des Frontends.

    Wie ``PUT /api/settings``: All-or-Nothing. Bei Validation-Errors
    wird nichts persistiert.
    """
    raw_payload = _payload_dict_or_none()
    if raw_payload is None or not isinstance(raw_payload, dict):
        return json_error(
            'invalid_payload', status=400, code='invalid_payload',
            message='PUT-Body muss ein JSON-Object sein.',
        )

    if raw_payload.get('confirm') is not True:
        return json_error(
            'confirm_required', status=400, code='confirm_required',
            message='Secrets können nur mit "confirm": true gesetzt werden.',
        )

    fields = raw_payload.get('fields', {})
    if not isinstance(fields, dict):
        return json_error(
            'invalid_payload', status=400, code='invalid_payload',
            message='"fields" muss ein JSON-Object sein.',
        )

    # Doppelter Schutz: jeder Key MUSS ein Secret-Feld sein. Der
    # Validator akzeptiert mit ``allow_secrets=True`` alles; die
    # Pflicht „nur Secrets hier" enforce-n wir einen Schritt früher,
    # damit eine versehentliche Vermischung lautstark scheitert.
    not_secret = [
        key for key in fields
        if (spec := field_by_key(str(key))) is None or not spec.secret
    ]
    if not_secret:
        return json_error(
            'non_secret_field', status=400, code='non_secret_field',
            message=(
                f'Folgende Felder sind keine Secrets und gehören auf '
                f'PUT /api/settings: {sorted(not_secret)}'
            ),
        )

    validated, errors = validate_payload(fields, allow_secrets=True)
    if errors:
        return _validation_error_response(errors)

    service = get_default_service()
    service.apply_payload(validated, persist=True)
    _publish_settings_changed(validated.keys(), source='settings.secrets')
    return json_success({
        'sections': list(SECTIONS),
        'fields': service.get_all_grouped(),
        'updated_keys': sorted(validated.keys()),
    })


def _validation_error_response(errors):
    payload = {
        'success': False,
        'error': 'validation_failed',
        'code': 'validation_failed',
        'errors': [e.to_dict() for e in errors],
    }
    from flask import jsonify
    return jsonify(payload), 400


def _publish_settings_changed(keys, *, source):
    try:
        publish_settings_changed(keys, source=source)
    except Exception as exc:
        logger.warning("settings.changed publish failed: %s", exc)
