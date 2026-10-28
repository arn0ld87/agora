"""
Validator helpers, backend constants, and environment utilities for app configuration.
"""

import os
from typing import TYPE_CHECKING, Any

from ._config_groups import (
    DECISION_LAYER_MODES,  # noqa: F401
    _get_cfg_attr,
)

if TYPE_CHECKING:
    from .security.supabase_jwt import SupabaseJwtSettings

# Bekannte Platzhalter-Werte aus `.env.example` und altem Default-Code.
# Wenn einer davon im Nicht-Debug-Betrieb durchschlägt, kennt das halbe
# Internet das Geheimnis — Config.validate() lehnt das deshalb ab.
SECRET_KEY_PLACEHOLDERS = frozenset({
    'change-me',
    'change-me-use-token_urlsafe-32',
    'agora',
    'password',
})
NEO4J_PASSWORD_PLACEHOLDERS = frozenset({
    'change-me',
    'agora',
    'neo4j',
    'password',
})

# Betreiber-Provider-Zugangsdaten, die die oeffentliche Demo-Instanz nie
# halten oder nutzen darf (Workspace-BYOK-Modell, #1688). Geteilte Liste fuer
# den Startup-Guard (siehe unten) und
# ``backend/scripts/bootstrap_public_demo_providers.py``.
DEMO_MODE_FORBIDDEN_ENV_VARS: tuple[str, ...] = (
    'LLM_API_KEY',
    'OPENAI_API_KEY',
    'GEMINI_API_KEY',
    'GOOGLE_API_KEY',
    'MINIMAX_API_KEY',
    'ANTHROPIC_API_KEY',
    'OPENROUTER_API_KEY',
    'OLLAMA_API_KEY',
    # Bedrock ist ebenfalls BYOK-faehig; ein Betreiber-Bearer-Token darf in
    # der Demo nie als Fallback bereitliegen.
    'AWS_BEARER_TOKEN_BEDROCK',
    # EMBEDDING_API_KEY fehlt bewusst: er gilt nur fuer den per
    # AGORA_SHARED_EMBEDDING_BASE_URL freigegebenen Betreiber-Endpoint (gns3).
    'LLM_BOOST_API_KEY',
    'LLM_BASE_URL',
    'LLM_BOOST_BASE_URL',
    # #1688 Runde 3: weitere Betreiber-Zugaenge, die ein Workspace-Lauf sonst
    # still mitbenutzen koennte (Web-Recherche, Claude-CLI-Session,
    # OpenAI-/Ollama-Endpunkte fuer OASIS und Legacy-Clients).
    # EMBEDDING_BASE_URL fehlt bewusst: Demo-Embeddings laufen ueber den
    # Betreiber-Endpoint auf gns3 (qwen3-embedding:4b, Runbook).
    'TAVILY_API_KEY',
    'CLAUDE_CODE_OAUTH_TOKEN',
    'OLLAMA_BASE_URL',
    'OPENAI_BASE_URL',
    'OPENAI_API_BASE_URL',
)


def is_demo_mode() -> bool:
    """``AGORA_DEMO_MODE``-Gate, identisches Muster zu
    ``app/api/simulation_common.py``/``app/services/llm_routing_seed.py``."""
    return os.environ.get('AGORA_DEMO_MODE', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def demo_mode_leaked_operator_vars() -> list[str]:
    """Namen der in ``AGORA_DEMO_MODE`` verbotenen, aber gesetzten Env-Vars.

    Nur Namen, nie Werte — auch nicht in Fehlermeldungen oder Logs.

    Prueft neben ``os.environ`` auch ``instance/settings.json``: der
    Settings-Layer legt Datei-Werte ueber die Env, ein dort persistierter
    Betreiber-Key waere sonst ein stiller Fallback trotz leerer ``.env``.
    """
    forbidden_vars = _get_cfg_attr('DEMO_MODE_FORBIDDEN_ENV_VARS', DEMO_MODE_FORBIDDEN_ENV_VARS)
    leaked = [
        name for name in forbidden_vars
        if (os.environ.get(name) or '').strip()
    ]
    from .services.settings_layer import get_default_service

    file_layer = get_default_service()._read_file_layer()
    for name in forbidden_vars:
        value = file_layer.get(name)
        if value is not None and str(value).strip():
            leaked.append(f'instance/settings.json:{name}')
    return leaked


# Metadaten-Backend (docs/plans/supabase.md §8). 'legacy' ist der heutige Weg:
# Dateisystem und Neo4j tragen die Wahrheit. 'postgres' schaltet ab Phase 4
# einzelne Stores auf die Datenbank um, Store fuer Store, nicht auf einmal.
METADATA_BACKENDS = frozenset({'legacy', 'postgres'})

# SQLAlchemy braucht den Treiber im Schema. 'postgresql://' allein waehlt
# psycopg2, das hier nicht installiert ist — der Fehler faellt sonst erst beim
# ersten Verbindungsversuch und mit einem Traceback, der nach einem fehlenden
# Paket aussieht statt nach einer falschen URL.
DATABASE_URL_PREFIX = 'postgresql+psycopg://'


def validate_database_settings(metadata_backend: str, database_url: str) -> list[str]:
    """Prüft AGORA_METADATA_BACKEND und DATABASE_URL gegeneinander.

    Steht als Modulfunktion und nicht als Methode in `Config`, damit die
    Verzweigungen nicht auf das Komplexitätsbudget von `Config.validate()`
    gehen — die Methode ist bereits an ihrer Allowlist-Grenze
    (`backend/radon-allowlist.txt`).
    """
    backends = _get_cfg_attr('METADATA_BACKENDS', METADATA_BACKENDS)
    url_prefix = _get_cfg_attr('DATABASE_URL_PREFIX', DATABASE_URL_PREFIX)
    backend = (metadata_backend or '').strip().lower()
    if backend not in backends:
        # Ein Tippfehler darf nicht still auf 'legacy' zurückfallen: das sieht
        # im Log aus wie eine bewusste Entscheidung und ist keine.
        return [
            f"AGORA_METADATA_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend != 'postgres':
        return []

    url = (database_url or '').strip()
    if not url:
        return [
            "AGORA_METADATA_BACKEND=postgres requires DATABASE_URL "
            "(e.g. postgresql+psycopg://user:password@host:5432/dbname)"
        ]

    if not url.startswith(url_prefix):
        return [
            f"DATABASE_URL must start with '{url_prefix}' — "
            "SQLAlchemy selects the driver from the scheme, and a bare "
            "'postgresql://' resolves to psycopg2, which is not installed"
        ]

    return []


#: Ablagen, die `AGORA_LLM_PROFILE_BACKEND` kennt. 'postgres' steht hier, weil
#: der Wert als Konfiguration schon gültig ist — der Adapter dazu kommt mit
#: PR 4 (docs/plans/supabase.md §10). Bis dahin lehnt die Validierung ihn mit
#: einem Satz ab, der sagt warum, statt mit einem Importfehler beim ersten
#: Profilzugriff.
LLM_PROFILE_BACKENDS = frozenset({'sqlite', 'postgres'})

#: Leer, seit PR 4 den PostgreSQL-Adapter mitbringt. Bleibt als Mechanik
#: stehen, weil der nächste Store denselben Zwischenzustand durchläuft: Wert
#: schon gültig, Adapter noch nicht da.
LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE: frozenset[str] = frozenset()


def validate_llm_profile_backend(llm_profile_backend: str) -> list[str]:
    """Prüft AGORA_LLM_PROFILE_BACKEND.

    Wie `validate_database_settings` eine Modulfunktion, damit die
    Verzweigungen nicht auf das Komplexitätsbudget von `Config.validate()`
    gehen.
    """
    backends = _get_cfg_attr('LLM_PROFILE_BACKENDS', LLM_PROFILE_BACKENDS)
    not_yet = _get_cfg_attr('LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE', LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE)
    backend = (llm_profile_backend or '').strip().lower()
    if backend not in backends:
        # Derselbe Grund wie bei AGORA_METADATA_BACKEND: ein Tippfehler darf
        # nicht still auf den Default zurückfallen.
        return [
            f"AGORA_LLM_PROFILE_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend in not_yet:
        return [
            f"AGORA_LLM_PROFILE_BACKEND={backend} is not available yet — "
            "the PostgreSQL adapter arrives with PR 4 "
            "(docs/plans/supabase.md §10). Use 'sqlite' until then; "
            "existing profiles stay where they are."
        ]

    return []


#: Ablagen, die `AGORA_PROJECT_BACKEND` kennt. Beide sind bedient, seit der
#: zweite Teil von PR 6 (docs/plans/supabase.md §11) den PostgreSQL-Adapter
#: mitbringt.
PROJECT_BACKENDS = frozenset({'file', 'postgres'})

#: Leer, seit der PostgreSQL-Adapter da ist. Bleibt als Mechanik stehen, weil
#: der nächste Store denselben Zwischenzustand durchläuft: Wert schon gültig,
#: Adapter noch nicht da — dieselbe Rolle wie
#: LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE zwischen PR 3 und PR 4.
PROJECT_BACKENDS_NOT_YET_AVAILABLE: frozenset[str] = frozenset()


def validate_project_backend(
    project_backend: str, database_url: str = ''
) -> list[str]:
    """Prüft AGORA_PROJECT_BACKEND.

    Modulfunktion aus demselben Grund wie `validate_llm_profile_backend`: die
    Verzweigungen sollen nicht auf das Komplexitätsbudget von
    `Config.validate()` gehen.
    """
    backends = _get_cfg_attr('PROJECT_BACKENDS', PROJECT_BACKENDS)
    not_yet = _get_cfg_attr('PROJECT_BACKENDS_NOT_YET_AVAILABLE', PROJECT_BACKENDS_NOT_YET_AVAILABLE)
    url_prefix = _get_cfg_attr('DATABASE_URL_PREFIX', DATABASE_URL_PREFIX)
    backend = (project_backend or '').strip().lower()
    if backend not in backends:
        # Ein Tippfehler darf nicht still auf den Default zurückfallen — sonst
        # arbeitet die Installation weiter auf der Datei, während der Betreiber
        # glaubt, er habe umgeschaltet.
        return [
            f"AGORA_PROJECT_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend in not_yet:
        return [
            f'AGORA_PROJECT_BACKEND={backend} is not available yet — '
            'the PostgreSQL adapter arrives with the second part of PR 6 '
            "(docs/plans/supabase.md §11). Use 'file' until then; "
            'existing projects stay where they are.'
        ]

    if backend == 'postgres' and not (database_url or '').strip():
        # Ohne URL scheiterte es sonst erst beim ersten Projektzugriff, und der
        # Fehler sähe dann nach einem Verbindungsproblem aus statt nach einer
        # fehlenden Einstellung.
        return [
            'AGORA_PROJECT_BACKEND=postgres requires DATABASE_URL '
            f'({url_prefix}user:password@host:5432/dbname)'
        ]

    return []


#: Ablagen, die `AGORA_SIMULATION_BACKEND` kennt (Issue #1585,
#: docs/plans/supabase.md §11, PR 7).
SIMULATION_BACKENDS = frozenset({'file', 'postgres'})


def validate_simulation_backend(
    simulation_backend: str,
    database_url: str = '',
    project_backend: str = 'file',
) -> list[str]:
    """Prueft AGORA_SIMULATION_BACKEND.

    Modulfunktion aus demselben Grund wie `validate_project_backend`: die
    Verzweigungen sollen nicht auf das Komplexitaetsbudget von
    `Config.validate()` gehen.

    Eine Besonderheit gegenueber `validate_project_backend`: `postgres`
    verlangt zusaetzlich `AGORA_PROJECT_BACKEND=postgres`. Die Tabelle
    `agora.simulations` traegt eine Fremdschluessel-Spalte auf
    `agora.projects(id)` — stuenden die Projekte weiter nur in der Datei,
    zeigte der Fremdschluessel bei jeder Simulation ins Leere.
    """
    backends = _get_cfg_attr('SIMULATION_BACKENDS', SIMULATION_BACKENDS)
    url_prefix = _get_cfg_attr('DATABASE_URL_PREFIX', DATABASE_URL_PREFIX)
    backend = (simulation_backend or '').strip().lower()
    if backend not in backends:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen —
        # sonst arbeitet die Installation weiter auf der Datei, waehrend der
        # Betreiber glaubt, er habe umgeschaltet.
        return [
            f"AGORA_SIMULATION_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend == 'postgres':
        normalized_project_backend = (project_backend or '').strip().lower()
        if normalized_project_backend != 'postgres':
            # Die FK-Spalte agora.simulations.project_id zeigt sonst auf eine
            # Tabelle, die niemand befuellt.
            return [
                'AGORA_SIMULATION_BACKEND=postgres requires '
                "AGORA_PROJECT_BACKEND=postgres (agora.simulations.project_id "
                'is a foreign key into agora.projects)'
            ]
        if not (database_url or '').strip():
            # Ohne URL scheiterte es sonst erst beim ersten Simulationszugriff,
            # und der Fehler sähe dann nach einem Verbindungsproblem aus statt
            # nach einer fehlenden Einstellung.
            return [
                'AGORA_SIMULATION_BACKEND=postgres requires DATABASE_URL '
                f'({url_prefix}user:password@host:5432/dbname)'
            ]

    return []


#: Ablagen, die `AGORA_RUN_BACKEND` kennt (Issue #1587,
#: docs/plans/supabase.md §11, PR 8).
RUN_BACKENDS = frozenset({'file', 'postgres'})


def validate_run_backend(
    run_backend: str,
    database_url: str = '',
    simulation_backend: str = 'file',
) -> list[str]:
    """Prueft AGORA_RUN_BACKEND.

    Modulfunktion aus demselben Grund wie `validate_simulation_backend`.
    `postgres` verlangt `AGORA_SIMULATION_BACKEND=postgres`: die Tabelle
    `agora.runs` traegt eine Fremdschluessel-Spalte auf
    `agora.simulations(id)` — stuenden die Simulationen weiter nur in der
    Datei, scheiterte jeder Run mit Simulationsbezug am Fremdschluessel.
    """
    backends = _get_cfg_attr('RUN_BACKENDS', RUN_BACKENDS)
    url_prefix = _get_cfg_attr('DATABASE_URL_PREFIX', DATABASE_URL_PREFIX)
    backend = (run_backend or '').strip().lower()
    if backend not in backends:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen.
        return [
            f"AGORA_RUN_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend == 'postgres':
        normalized_simulation_backend = (simulation_backend or '').strip().lower()
        if normalized_simulation_backend != 'postgres':
            return [
                'AGORA_RUN_BACKEND=postgres requires '
                "AGORA_SIMULATION_BACKEND=postgres (agora.runs.simulation_id "
                'is a foreign key into agora.simulations)'
            ]
        if not (database_url or '').strip():
            return [
                'AGORA_RUN_BACKEND=postgres requires DATABASE_URL '
                f'({url_prefix}user:password@host:5432/dbname)'
            ]

    return []


#: Ablagen, die `AGORA_REPORT_BACKEND` kennt (Issue #1588,
#: docs/plans/supabase.md §11, PR 9).
REPORT_BACKENDS = frozenset({'file', 'postgres'})


def validate_report_backend(
    report_backend: str,
    database_url: str = '',
    simulation_backend: str = 'file',
) -> list[str]:
    """Prueft AGORA_REPORT_BACKEND.

    Modulfunktion aus demselben Grund wie `validate_run_backend`. `postgres`
    verlangt `AGORA_SIMULATION_BACKEND=postgres`: `agora.reports` traegt eine
    Fremdschluessel-Spalte auf `agora.simulations(id)`.
    """
    backends = _get_cfg_attr('REPORT_BACKENDS', REPORT_BACKENDS)
    url_prefix = _get_cfg_attr('DATABASE_URL_PREFIX', DATABASE_URL_PREFIX)
    backend = (report_backend or '').strip().lower()
    if backend not in backends:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen.
        return [
            f"AGORA_REPORT_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend == 'postgres':
        normalized_simulation_backend = (simulation_backend or '').strip().lower()
        if normalized_simulation_backend != 'postgres':
            return [
                'AGORA_REPORT_BACKEND=postgres requires '
                "AGORA_SIMULATION_BACKEND=postgres (agora.reports.simulation_id "
                'is a foreign key into agora.simulations)'
            ]
        if not (database_url or '').strip():
            return [
                'AGORA_REPORT_BACKEND=postgres requires DATABASE_URL '
                f'({url_prefix}user:password@host:5432/dbname)'
            ]

    return []


#: Ablagen, die `AGORA_PERSONA_SET_BACKEND` kennt (Issue #1807, Etappe 7).
PERSONA_SET_BACKENDS = frozenset({'file', 'postgres'})


def validate_persona_set_backend(
    persona_set_backend: str,
    database_url: str = '',
) -> list[str]:
    """Prueft AGORA_PERSONA_SET_BACKEND.

    Modulfunktion aus demselben Grund wie `validate_report_backend`. Anders
    als Simulationen, Runs und Reports hat `agora.persona_sets` **keinen**
    Fremdschluessel auf eine andere Metadaten-Tabelle (`graph_id`,
    `project_id` und die Simulationskennungen sind reine Verweise im Satz).
    `postgres` verlangt deshalb nur `DATABASE_URL`, keinen anderen Schalter.
    """
    backends = _get_cfg_attr('PERSONA_SET_BACKENDS', PERSONA_SET_BACKENDS)
    url_prefix = _get_cfg_attr('DATABASE_URL_PREFIX', DATABASE_URL_PREFIX)
    backend = (persona_set_backend or '').strip().lower()
    if backend not in backends:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen.
        return [
            f"AGORA_PERSONA_SET_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    if backend == 'postgres' and not (database_url or '').strip():
        return [
            'AGORA_PERSONA_SET_BACKEND=postgres requires DATABASE_URL '
            f'({url_prefix}user:password@host:5432/dbname)'
        ]

    return []


#: Auth-Modi (ADR-0018, Issue #1613). ``legacy`` ist der Pfad vor ADR-0018,
#: ``hybrid`` nimmt zusaetzlich Supabase-JWTs an, ``supabase`` lehnt den
#: Master-Token ab.
AUTH_BACKENDS = frozenset({'legacy', 'hybrid', 'supabase'})

#: Die Metadaten-Schalter, die fuer JWT-Nutzer alle auf ``postgres`` stehen
#: muessen. Die Datei-Backends kennen keine Workspaces; mit einem von ihnen
#: saehe ein angemeldeter Nutzer die Daten aller anderen (ADR-0018, Punkt 3).
WORKSPACE_SCOPED_BACKENDS: tuple[tuple[str, str], ...] = (
    ('AGORA_LLM_PROFILE_BACKEND', 'LLM_PROFILE_BACKEND'),
    ('AGORA_PROJECT_BACKEND', 'PROJECT_BACKEND'),
    ('AGORA_SIMULATION_BACKEND', 'SIMULATION_BACKEND'),
    ('AGORA_RUN_BACKEND', 'RUN_BACKEND'),
    ('AGORA_REPORT_BACKEND', 'REPORT_BACKEND'),
    ('AGORA_PERSONA_SET_BACKEND', 'PERSONA_SET_BACKEND'),
)


def validate_master_token_policy(debug: bool, auth_backend: str) -> list[str]:
    """Ausserhalb von FLASK_DEBUG: Token oder bewusstes Opt-out.

    Verhindert offene ``/api/*``-Deployments durch reines „Token vergessen“.
    Im Modus ``supabase`` gibt es keinen Master-Token; die Identitaet kommt
    aus dem JWT (``validate_auth_backend`` verlangt dessen Konfiguration).
    """
    if debug or (auth_backend or '').strip().lower() == 'supabase':
        return []
    auth_token = os.environ.get('AGORA_AUTH_TOKEN', '').strip()
    allow_anon = os.environ.get('AGORA_ALLOW_ANONYMOUS', 'false').lower() in ('true', '1', 'yes')
    if not auth_token and not allow_anon:
        return [
            "AGORA_AUTH_TOKEN missing in non-debug mode "
            "(set AGORA_ALLOW_ANONYMOUS=true to opt out explicitly)"
        ]
    return []


#: Filtern die Repositories nach ``workspace_id``? Seit #1614 ja: Projekte,
#: Simulationen, Runs und Reports sind workspace-gebunden, und der Guard
#: prueft jede Kennung im Request (``app/security/resource_guard.py``).
#: Ohne diese Isolation darf kein JWT-Nutzer zugelassen werden.
TENANT_ISOLATION_AVAILABLE = True


def supabase_jwt_configured(config: Any) -> bool:
    """``True``, sobald ein Issuer gesetzt ist — ab dann gilt die Invariante."""
    return bool((getattr(config, 'SUPABASE_JWT_ISSUER', '') or '').strip())


def supabase_jwt_settings(config: Any) -> 'SupabaseJwtSettings | None':
    """Die Pruef-Einstellungen oder ``None``, wenn JWT nicht konfiguriert ist.

    Wirft ``ValueError`` bei unvollstaendiger Konfiguration; ``validate()``
    faengt das vorher ab.
    """
    from pydantic import SecretStr

    from .security.supabase_jwt import SupabaseJwtSettings

    if not supabase_jwt_configured(config):
        return None
    secret = (getattr(config, 'SUPABASE_JWT_SECRET', '') or '').strip()
    jwks_url = (getattr(config, 'SUPABASE_JWKS_URL', '') or '').strip()
    return SupabaseJwtSettings(
        issuer=config.SUPABASE_JWT_ISSUER.strip(),
        audience=(getattr(config, 'SUPABASE_JWT_AUDIENCE', '') or 'authenticated').strip(),
        jwks_url=jwks_url or None,
        secret=SecretStr(secret) if secret else None,
    )


def validate_auth_backend(config: Any) -> list[str]:
    """Prueft ``AGORA_AUTH_BACKEND`` und die JWT-Einstellungen (ADR-0018).

    * Ein unbekannter Modus ist ein Fehler, kein Rueckfall auf ``legacy``.
    * JWT-Einstellungen ohne Issuer sind halb konfiguriert und damit ein
      Fehler — sonst waere unklar, ob der JWT-Zweig aktiv ist.
    * Mit JWT muessen alle fuenf Metadaten-Schalter auf ``postgres`` stehen
      und ``DATABASE_URL`` gesetzt sein; ``legacy`` mit JWT ist ein
      Widerspruch, ``supabase`` ohne JWT sperrt jeden Nutzer aus.
    * Mit JWT gibt es keinen offenen Modus: ``AGORA_ALLOW_ANONYMOUS`` waere
      ein Principal ohne Identitaet im Default-Workspace.
    """
    backends = _get_cfg_attr('AUTH_BACKENDS', AUTH_BACKENDS)
    backend = (getattr(config, 'AUTH_BACKEND', '') or '').strip().lower()
    if backend not in backends:
        return [
            f"AGORA_AUTH_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(backends))})"
        ]

    configured = supabase_jwt_configured(config)
    if not configured:
        stray = [
            env_name
            for env_name, attr in (
                ('AGORA_SUPABASE_JWKS_URL', 'SUPABASE_JWKS_URL'),
                ('AGORA_SUPABASE_JWT_SECRET', 'SUPABASE_JWT_SECRET'),
            )
            if (getattr(config, attr, '') or '').strip()
        ]
        if stray:
            return [
                f"{', '.join(stray)} set without AGORA_SUPABASE_JWT_ISSUER "
                '(JWT verification is either fully configured or off)'
            ]
        if backend == 'supabase':
            return [
                'AGORA_AUTH_BACKEND=supabase requires Supabase JWT settings '
                '(AGORA_SUPABASE_JWT_ISSUER plus AGORA_SUPABASE_JWKS_URL or '
                'AGORA_SUPABASE_JWT_SECRET)'
            ]
        return []

    errors: list[str] = []
    # Dynamic lookup via app.config module if loaded, so tests monkeypatching
    # 'app.config.TENANT_ISOLATION_AVAILABLE' continue to work seamlessly.
    tenant_avail = _get_cfg_attr('TENANT_ISOLATION_AVAILABLE', TENANT_ISOLATION_AVAILABLE)
    if not tenant_avail:
        errors.append(
            'Supabase JWT auth is not available yet: repositories do not filter '
            'by workspace until #1614 — unset AGORA_SUPABASE_JWT_ISSUER'
        )
    if backend == 'legacy':
        errors.append(
            'AGORA_AUTH_BACKEND=legacy ignores Supabase JWT settings — use '
            'hybrid or supabase, or unset AGORA_SUPABASE_JWT_ISSUER'
        )
    from pydantic import ValidationError

    try:
        supabase_jwt_settings(config)
    except ValidationError as exc:
        # Nur die Regeltexte: ``str(exc)`` enthielte die Eingabe und damit
        # das Secret im Klartext.
        reasons = '; '.join(
            str(err['msg'])
            for err in exc.errors(include_url=False, include_input=False, include_context=False)
        )
        errors.append(f'Supabase JWT settings invalid: {reasons}')

    errors.extend(_tenant_isolation_errors(config))
    return errors


def _tenant_isolation_errors(config: Any) -> list[str]:
    """Was mit aktivem JWT die Workspace-Grenze aufweichen würde: Datei-Backends,
    fehlende Datenbank, offener Modus, beliebige Origins."""
    errors: list[str] = []
    workspace_scoped = _get_cfg_attr('WORKSPACE_SCOPED_BACKENDS', WORKSPACE_SCOPED_BACKENDS)
    not_postgres = [
        env_name
        for env_name, attr in workspace_scoped
        if (getattr(config, attr, '') or '').strip().lower() != 'postgres'
    ]
    if not_postgres:
        errors.append(
            'Supabase JWT auth requires every metadata backend on postgres '
            '(file backends have no workspace isolation); not postgres: '
            + ', '.join(not_postgres)
        )
    if not (getattr(config, 'DATABASE_URL', '') or '').strip():
        errors.append('Supabase JWT auth requires DATABASE_URL')
    if os.environ.get('AGORA_ALLOW_ANONYMOUS', 'false').lower() in ('true', '1', 'yes'):
        errors.append(
            'AGORA_ALLOW_ANONYMOUS cannot be combined with Supabase JWT auth'
        )
    if os.environ.get('AGORA_CORS_ALLOW_ALL', 'false').lower() == 'true':
        # Mit Registrierung für jeden darf keine fremde Origin im Namen eines
        # angemeldeten Nutzers Anfragen stellen (Plan §37, #1616).
        errors.append('AGORA_CORS_ALLOW_ALL cannot be combined with Supabase JWT auth')
    return errors
