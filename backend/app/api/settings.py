"""Settings API (Issue #133, SUB1).

Liefert das deklarative Settings-Schema und die aktuellen, je Quelle
markierten Werte. Schreib-Routen folgen in SUB2.

Endpunkte (alle hinter dem Standard-Blueprint-Guard, d. h.
``AGORA_AUTH_TOKEN`` Pflicht außerhalb von ``FLASK_DEBUG=true``):

  - ``GET /api/settings``        — alle Felder gruppiert nach Sektion
  - ``GET /api/settings/schema`` — nur Meta (Typ, Default, Enum, Flags)

Begründung für die Trennung Schema ↔ Werte: das Frontend lädt einmal
das Schema (cachebar), pollt dann nur die Werte; das spart bei großen
Settings-Listen Bandbreite und macht den Schema-Cache im Store
testbar.
"""

from __future__ import annotations

from flask import Blueprint

from ..services.settings_layer import get_default_service
from ..services.settings_schema import SECTIONS
from ..utils.api_responses import handle_api_errors, json_success


settings_bp = Blueprint('settings', __name__)


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
