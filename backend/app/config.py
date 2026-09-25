"""
Configuration Management
Loads configuration from .env file in project root directory
"""

import json
import os
from typing import TYPE_CHECKING, Any
from dotenv import load_dotenv

if TYPE_CHECKING:
    from .security.supabase_jwt import SupabaseJwtSettings


KNOWN_EMBEDDING_DIMS = {
    'nomic-embed-text': 768,
    'embeddinggemma:300m': 768,
    'all-minilm': 384,
    'bge-m3': 1024,
    'text-embedding-3-small': 1536,
    'text-embedding-ada-002': 1536,
    'text-embedding-3-large': 3072,
    'qwen3-embedding:4b': 2560,
    'qwen3-embedding:8b': 4096,
    'gemini-embedding-2': 3072,
    # gemini-embedding-001 liefert per Default 3072 Dimensionen (Matryoshka,
    # per output_dimensionality auf 1536/768 kuerzbar — der OpenAI-Compat-Pfad
    # in EmbeddingService sendet diesen Parameter nicht, also gilt 3072).
    'gemini-embedding-001': 3072,
}

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
    backend = (metadata_backend or '').strip().lower()
    if backend not in METADATA_BACKENDS:
        # Ein Tippfehler darf nicht still auf 'legacy' zurückfallen: das sieht
        # im Log aus wie eine bewusste Entscheidung und ist keine.
        return [
            f"AGORA_METADATA_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(METADATA_BACKENDS))})"
        ]

    if backend != 'postgres':
        return []

    url = (database_url or '').strip()
    if not url:
        return [
            "AGORA_METADATA_BACKEND=postgres requires DATABASE_URL "
            "(e.g. postgresql+psycopg://user:password@host:5432/dbname)"
        ]

    if not url.startswith(DATABASE_URL_PREFIX):
        return [
            f"DATABASE_URL must start with '{DATABASE_URL_PREFIX}' — "
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
    backend = (llm_profile_backend or '').strip().lower()
    if backend not in LLM_PROFILE_BACKENDS:
        # Derselbe Grund wie bei AGORA_METADATA_BACKEND: ein Tippfehler darf
        # nicht still auf den Default zurückfallen.
        return [
            f"AGORA_LLM_PROFILE_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(LLM_PROFILE_BACKENDS))})"
        ]

    if backend in LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE:
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
    backend = (project_backend or '').strip().lower()
    if backend not in PROJECT_BACKENDS:
        # Ein Tippfehler darf nicht still auf den Default zurückfallen — sonst
        # arbeitet die Installation weiter auf der Datei, während der Betreiber
        # glaubt, er habe umgeschaltet.
        return [
            f"AGORA_PROJECT_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(PROJECT_BACKENDS))})"
        ]

    if backend in PROJECT_BACKENDS_NOT_YET_AVAILABLE:
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
            f'({DATABASE_URL_PREFIX}user:password@host:5432/dbname)'
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
    backend = (simulation_backend or '').strip().lower()
    if backend not in SIMULATION_BACKENDS:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen —
        # sonst arbeitet die Installation weiter auf der Datei, waehrend der
        # Betreiber glaubt, er habe umgeschaltet.
        return [
            f"AGORA_SIMULATION_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(SIMULATION_BACKENDS))})"
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
                f'({DATABASE_URL_PREFIX}user:password@host:5432/dbname)'
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
    backend = (run_backend or '').strip().lower()
    if backend not in RUN_BACKENDS:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen.
        return [
            f"AGORA_RUN_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(RUN_BACKENDS))})"
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
                f'({DATABASE_URL_PREFIX}user:password@host:5432/dbname)'
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
    backend = (report_backend or '').strip().lower()
    if backend not in REPORT_BACKENDS:
        # Ein Tippfehler darf nicht still auf die Dateiablage zurueckfallen.
        return [
            f"AGORA_REPORT_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(REPORT_BACKENDS))})"
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
                f'({DATABASE_URL_PREFIX}user:password@host:5432/dbname)'
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
    backend = (getattr(config, 'AUTH_BACKEND', '') or '').strip().lower()
    if backend not in AUTH_BACKENDS:
        return [
            f"AGORA_AUTH_BACKEND has unknown value '{backend}' "
            f"(expected one of: {', '.join(sorted(AUTH_BACKENDS))})"
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
    if not TENANT_ISOLATION_AVAILABLE:
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
    not_postgres = [
        env_name
        for env_name, attr in WORKSPACE_SCOPED_BACKENDS
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

#: f005 (ADR-0016): globaler Zustand der Decision-Layer-Pilotierung. Ein
#: einziger Pilot-Use-Case in dieser Slice — je-Use-Case-Granularitaet ist
#: ausdruecklich zukuenftige Arbeit (ADR-0016, "Was dieser Entwurf nicht
#: entscheidet"), kein vorgezogener Mechanismus dafuer.
#: 'disabled': kein Provider wird aufgerufen, bestehendes Verhalten
#:   unveraendert (Default).
#: 'shadow': ein Kandidat (z. B. Jev) laeuft parallel zur bestehenden
#:   autoritativen Entscheidung, ergebnis wird NICHT verwendet.
#: 'authoritative': erst nach bestandenem Benchmark und jev-choice-Gate.
DECISION_LAYER_MODES = frozenset({'disabled', 'shadow', 'authoritative'})


def validate_decision_layer_mode(mode: str) -> list[str]:
    """Prüft AGORA_DECISION_LAYER_MODE. Modulfunktion aus demselben Grund
    wie `validate_project_backend`.

    Review-Befund (Codex, PR #1547): `authoritative` war ein erkannter,
    aber unbenutzter Wert — Startvalidierung akzeptierte ihn, obwohl der
    einzige verdrahtete Use Case (`local_search_shadow.py`) bei jedem
    Wert außer `shadow` sofort zurückkehrt. Ein Betreiber, der
    `AGORA_DECISION_LAYER_MODE=authoritative` setzt, hätte einen
    erfolgreichen Start und einen still inaktiven Decision Layer bekommen
    — genau die Verwechslung von Zustand und Anzeige, die ADR-0002 an
    anderer Stelle ausschließt. `authoritative` bleibt ein gültiger Wert
    im Vokabular (`DECISION_LAYER_MODES`), wird aber als Konfigurationsfehler
    abgelehnt, bis ein echter Handler existiert (erst nach bestandenem
    Benchmark und `jev-choice`-Gate, siehe Moduldoc oben)."""
    normalized = (mode or '').strip().lower()
    if normalized not in DECISION_LAYER_MODES:
        return [
            f"AGORA_DECISION_LAYER_MODE has unknown value '{normalized}' "
            f"(expected one of: {', '.join(sorted(DECISION_LAYER_MODES))})"
        ]
    if normalized == 'authoritative':
        return [
            "AGORA_DECISION_LAYER_MODE=authoritative is not usable yet: no "
            "wired use case has an authoritative handler (jev-choice gate "
            "not passed). Starting with this value would succeed while the "
            "Decision Layer silently stays inactive, which is worse than "
            "refusing to start. Use 'shadow' or 'disabled' instead."
        ]
    return []


def validate_job_lease_timing(
    ttl_s: float, heartbeat_interval_s: float, max_stall_s: float
) -> list[str]:
    """Prüft die Job-Lease-Zeiten (Issue #1472, Codex-P2 PR #1555).

    Ein Intervall von 0 ließe den Heartbeat-Loop ohne Pause drehen; ein
    Intervall nahe der TTL ließe die Lease schon bei einem einzigen
    verspäteten Tick verfallen und gäbe einen laufenden Job zum Doppelstart
    frei. Deshalb: alle Werte > 0 und Intervall höchstens TTL/2."""
    errors = [
        f"{name} must be > 0 (got {value})"
        for name, value in (
            ('AGORA_JOB_LEASE_TTL_SECONDS', ttl_s),
            ('AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS', heartbeat_interval_s),
            ('AGORA_JOB_LEASE_MAX_STALL_SECONDS', max_stall_s),
        )
        if value <= 0
    ]
    if not errors and heartbeat_interval_s * 2 > ttl_s:
        errors.append(
            "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS must be at most half of "
            f"AGORA_JOB_LEASE_TTL_SECONDS (got interval {heartbeat_interval_s}, "
            f"ttl {ttl_s})"
        )
    return errors


def infer_vector_dim_for_model(model_name: str | None) -> int | None:
    """Infer a known vector dimension from the embedding model name."""
    normalized = (model_name or '').strip().lower()
    if not normalized:
        return None

    for known_model, dim in KNOWN_EMBEDDING_DIMS.items():
        if normalized == known_model or normalized.startswith(known_model):
            return dim

    return None

# Load .env file from project root
# Path: Agora/.env (relative to backend/app/config.py)
# Important: do not override already-exported environment variables.
# Docker Compose relies on process env overrides (e.g. host.docker.internal
# instead of localhost) and those must win over values from the host-side .env.
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=False)
else:
    # If no .env in root, try to load environment variables (for production)
    load_dotenv(override=False)


class Config:
    """Flask configuration class"""

    # Flask configuration
    # SECRET_KEY: kein Default in Code — muss per Env gesetzt sein. Fehlt er,
    # schreiben wir einen Prozess-lokalen Zufallswert ein, damit der Server
    # nicht startet mit dem öffentlich bekannten String. validate() warnt.
    SECRET_KEY = os.environ.get('SECRET_KEY') or ''
    # DEBUG default False — Tracebacks in API-Responses hängen an diesem Flag.
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    # JSON configuration - disable ASCII escaping to display Chinese directly (not as \uXXXX)
    JSON_AS_ASCII = False

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')
    # Leerer Default: Operator MUSS ein Modell setzen (ENV oder Settings-UI)
    # oder ein LLM-Profil anlegen. Vorher führte `qwen2.5:32b` in Cloud-Setups
    # (Ollama Cloud / OpenAI / Gemini) zu 404, weil das Auto-Bootstrap-Profil
    # auf ein lokales Tag verwies, das im aktiven Backend nicht existiert.
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', '')
    # Completion-Limit fuer einzelne LLM-Antworten. CAMEL verwendet dieses
    # Feld leider auch als Default fuer sein Memory-Token-Limit, deshalb
    # trennen wir die eigentliche Memory-Grenze unten separat.
    LLM_MAX_OUTPUT_TOKENS = int(os.environ.get('LLM_MAX_OUTPUT_TOKENS', '8192'))
    # Default-Memory-Budget fuer OASIS/CAMEL. Dieses Limit steuert, wie viel
    # Verlauf + Persona im Agent-Memory gehalten werden darf; es ist nicht
    # gleichbedeutend mit einem verlässlichen Ollama-/v1-num_ctx Override.
    LLM_CONTEXT_LIMIT = int(os.environ.get('LLM_CONTEXT_LIMIT', '262144'))
    try:
        LLM_MODEL_CONTEXT_LIMITS = json.loads(
            os.environ.get('LLM_MODEL_CONTEXT_LIMITS_JSON', '{}')
        )
    except json.JSONDecodeError:
        LLM_MODEL_CONTEXT_LIMITS = {}

    # Neo4j configuration
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    # No insecure default password. Must be provided via environment (.env / secret manager).
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', '')

    # Neo4j driver pool configuration. NEO4J_LIVENESS_TIMEOUT is the key
    # knob: before lending a pooled connection that has been idle longer
    # than this many seconds, the driver does a RESET round-trip to weed
    # out stale sockets that Docker bridge / conntrack already killed
    # silently. Without it, parallel persona generation hits a Bolt
    # socket-storm on the first burst after fork-idle.
    NEO4J_MAX_POOL_SIZE = int(os.environ.get('NEO4J_MAX_POOL_SIZE', '50'))
    NEO4J_ACQ_TIMEOUT = float(os.environ.get('NEO4J_ACQ_TIMEOUT', '60.0'))
    NEO4J_CONN_TIMEOUT = float(os.environ.get('NEO4J_CONN_TIMEOUT', '15.0'))
    NEO4J_MAX_LIFETIME = int(os.environ.get('NEO4J_MAX_LIFETIME', '3600'))
    NEO4J_LIVENESS_TIMEOUT = float(os.environ.get('NEO4J_LIVENESS_TIMEOUT', '30.0'))

    # PostgreSQL-Grundlage (docs/plans/supabase.md §8). Beides ist in dieser
    # Phase ohne Wirkung auf den Laufzeitpfad: AGORA_METADATA_BACKEND schaltet
    # erst ab Phase 4 einzelne Stores um, und solange er auf 'legacy' steht,
    # wird nie eine Verbindung aufgebaut.
    #
    # Kein Default fuer DATABASE_URL. Ein geratener localhost-Wert waere genau
    # der Legacy-Fallback, den die Architekturregel verbietet: er wuerde eine
    # fehlende Konfiguration als funktionierende ausgeben und im Containerpfad
    # auf den Container selbst zeigen. Fehlt der Wert, sagt validate() das.
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    METADATA_BACKEND = os.environ.get('AGORA_METADATA_BACKEND', 'legacy').strip().lower()

    # Ablage der LLM-Profile (docs/plans/supabase.md §10, PR 3). Getrennt von
    # METADATA_BACKEND, weil die Stores einzeln umgestellt werden — ein
    # Schalter fuer alles waere genau die Migration in einem Schritt, die der
    # Plan vermeidet. Default 'sqlite': instance/llm_profiles.db bleibt die
    # Wahrheit, bis PR 4 den PostgreSQL-Adapter bringt.
    LLM_PROFILE_BACKEND = os.environ.get(
        'AGORA_LLM_PROFILE_BACKEND', 'sqlite'
    ).strip().lower()

    # Ablage der Projekt-Metadaten (docs/plans/supabase.md §11, PR 6). Wieder
    # ein eigener Schalter aus demselben Grund wie bei den LLM-Profilen: die
    # Stores werden einzeln umgestellt. Default 'file' — der Inhalt von
    # uploads/projects/<project_id>/project.json bleibt die Wahrheit, bis der
    # PostgreSQL-Adapter da ist. Artefakte im selben Verzeichnis sind von
    # diesem Schalter nie betroffen.
    PROJECT_BACKEND = os.environ.get(
        'AGORA_PROJECT_BACKEND', 'file'
    ).strip().lower()

    # Ablage der Simulationsmetadaten (docs/plans/supabase.md §11, PR 7).
    # Eigener Schalter wie bei den Projekten. Default 'file' — der Inhalt von
    # uploads/simulations/<simulation_id>/state.json bleibt die Wahrheit.
    # 'postgres' setzt AGORA_PROJECT_BACKEND=postgres voraus (Fremdschluessel).
    SIMULATION_BACKEND = os.environ.get(
        'AGORA_SIMULATION_BACKEND', 'file'
    ).strip().lower()

    # Ablage der Run-Manifeste (docs/plans/supabase.md §11, PR 8). Eigener
    # Schalter wie bei den Simulationen. Default 'file' — die Manifeste unter
    # uploads/run_registry/<run_id>.json bleiben die Wahrheit.
    # 'postgres' setzt AGORA_SIMULATION_BACKEND=postgres voraus (Fremdschluessel).
    RUN_BACKEND = os.environ.get(
        'AGORA_RUN_BACKEND', 'file'
    ).strip().lower()

    # Ablage der Report-Metadaten (docs/plans/supabase.md §11, PR 9). Default
    # 'file' — uploads/reports/<report_id>/meta.json bleibt die Wahrheit.
    # Report-Inhalte bleiben in jedem Fall Dateien. 'postgres' setzt
    # AGORA_SIMULATION_BACKEND=postgres voraus (Fremdschluessel).
    REPORT_BACKEND = os.environ.get(
        'AGORA_REPORT_BACKEND', 'file'
    ).strip().lower()

    # Auth-Modus (ADR-0018, Issue #1613). Default 'hybrid': Supabase-JWTs
    # werden angenommen, sobald AGORA_SUPABASE_JWT_ISSUER gesetzt ist; ohne
    # diese Einstellung verhaelt sich 'hybrid' exakt wie 'legacy'.
    AUTH_BACKEND = os.environ.get('AGORA_AUTH_BACKEND', 'hybrid').strip().lower()
    SUPABASE_JWT_ISSUER = os.environ.get('AGORA_SUPABASE_JWT_ISSUER', '')
    SUPABASE_JWT_AUDIENCE = os.environ.get('AGORA_SUPABASE_JWT_AUDIENCE', 'authenticated')
    SUPABASE_JWKS_URL = os.environ.get('AGORA_SUPABASE_JWKS_URL', '')
    SUPABASE_JWT_SECRET = os.environ.get('AGORA_SUPABASE_JWT_SECRET', '')
    # Öffentliche Angaben für den Supabase-Client im Browser (#1616):
    # Gateway-URL und Anon-Key. Beides ist für den Browser bestimmt und kein
    # Geheimnis; ``GET /api/auth/config`` gibt es nur bei aktivem JWT aus.
    SUPABASE_URL = os.environ.get('AGORA_SUPABASE_URL', '')
    SUPABASE_ANON_KEY = os.environ.get('AGORA_SUPABASE_ANON_KEY', '')

    # f005 (ADR-0016): Decision-Layer-Pilotierung, Default 'disabled' haelt
    # jeden bestehenden Use-Case-Pfad unveraendert.
    DECISION_LAYER_MODE = os.environ.get(
        'AGORA_DECISION_LAYER_MODE', 'disabled'
    ).strip().lower()

    # Agent tool-use during simulation. Experimental and intentionally opt-in.
    ENABLE_AGENT_TOOLS = os.environ.get('ENABLE_AGENT_TOOLS', 'false').lower() in ('true', '1', 'yes')
    MAX_TOOL_CALLS_PER_ACTION = int(os.environ.get('MAX_TOOL_CALLS_PER_ACTION', '2'))

    # Embedding configuration. VECTOR_DIM muss zur Ausgabe des EMBEDDING_MODEL passen
    # (nomic-embed-text: 768, embeddinggemma:300m: 768, qwen3-embedding:4b: 2560,
    # qwen3-embedding:8b: 4096). Falsche Dim → Neo4j-Index stream rejected.
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434')
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY')
    VECTOR_DIM = int(
        os.environ.get(
            'VECTOR_DIM',
            str(infer_vector_dim_for_model(EMBEDDING_MODEL) or 768),
        )
    )

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = int(os.environ.get('GRAPH_CHUNK_SIZE', '1500'))
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get('GRAPH_CHUNK_OVERLAP', '150'))
    # Parallelism for GraphRAG NER/RE extraction (per-chunk LLM calls).
    GRAPH_PARALLEL_CHUNKS = int(os.environ.get('GRAPH_PARALLEL_CHUNKS', '4'))

    # Ontology generation. Agora no longer uses the old Zep custom-type cap,
    # but very large type lists make LLM extraction noisier. Keep defaults
    # conservative and configurable per deployment.
    ONTOLOGY_MIN_ENTITY_TYPES = int(os.environ.get('ONTOLOGY_MIN_ENTITY_TYPES', '8'))
    ONTOLOGY_MAX_ENTITY_TYPES = int(os.environ.get('ONTOLOGY_MAX_ENTITY_TYPES', '16'))
    ONTOLOGY_MAX_EDGE_TYPES = int(os.environ.get('ONTOLOGY_MAX_EDGE_TYPES', '12'))

    # Qualitätsschwellen für den fertigen Graph-Build (Issue #1029).
    # Ein Build, der technisch durchläuft, aber unterhalb dieser Werte
    # bleibt, meldete bislang "Graph fertig" und ließ den Report Schritte
    # später an fehlender Evidenz scheitern — an einem Symptom, dessen
    # Ursache hier liegt.
    #
    # GRAPH_MIN_RELATIONS auf 1: ein Graph ohne eine einzige Kante ist
    # keine Wissensbasis, sondern eine Stichwortliste. Das ist der Fall aus
    # Befund B-24 (3 Entitäten, 0 Beziehungen) und blockiert hart.
    GRAPH_MIN_ENTITIES = int(os.environ.get('GRAPH_MIN_ENTITIES', '3'))
    GRAPH_MIN_RELATIONS = int(os.environ.get('GRAPH_MIN_RELATIONS', '1'))
    # Anteil der Chunks, die mindestens eine Entität oder Relation liefern
    # müssen. Bei B-24 meldeten zwei von vier Chunks "0 entities, 0
    # relations" — die Hälfte des Dokuments war damit nicht erfasst, ohne
    # dass die Gesamtzahlen das verraten hätten. 0.0 schaltet die Prüfung ab.
    GRAPH_MIN_CHUNK_SUCCESS_RATIO = float(
        os.environ.get('GRAPH_MIN_CHUNK_SUCCESS_RATIO', '0.5')
    )

    # Hybrid search weights (SearchService — vector × keyword/BM25 mix).
    # Defaults reproduce the historical 0.7 / 0.3 split. The two weights do
    # not have to sum to 1; SearchService normalises within each side first.
    HYBRID_SEARCH_VECTOR_WEIGHT = float(os.environ.get('HYBRID_SEARCH_VECTOR_WEIGHT', '0.7'))
    HYBRID_SEARCH_KEYWORD_WEIGHT = float(os.environ.get('HYBRID_SEARCH_KEYWORD_WEIGHT', '0.3'))

    # GraphMemoryUpdater bounded queue — upper bound on buffered agent activities
    # waiting for Neo4j ingestion. Hitting this cap applies backpressure to the
    # OASIS subprocess (blocks briefly, then drops). Prevents OOM when the LLM
    # ingestion is slower than the simulation event rate.
    GRAPH_MEMORY_QUEUE_MAX = int(os.environ.get('GRAPH_MEMORY_QUEUE_MAX', '10000'))
    GRAPH_MEMORY_PUT_TIMEOUT = float(os.environ.get('GRAPH_MEMORY_PUT_TIMEOUT', '2.0'))

    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # OASIS platform available actions configuration
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent configuration
    # REPORT_TOOLCALL_MODE: "native" nutzt OpenAI function-calling (tools=/tool_choice=);
    # "xml" behält den Legacy-XML-Parsing-Pfad (<tool_call>...</tool_call>).
    # Default: "native" — Modelle wie deepseek-v4-flash:cloud senden keinen sauberen XML-Block.
    # Casing-tolerant + Whitelist: ungültige Werte fallen auf den Default "native"
    # zurück, nicht auf "xml". Begründung: ein Tippfehler ist ein Konfigurationsfehler
    # und soll sich verhalten wie "nicht konfiguriert" — nicht wie ein stiller
    # Moduswechsel. Der frühere xml-Fallback war als "legacy-stable" gedacht, trug
    # aber nicht: wer die Variable gar nicht setzt, landet ohnehin im native-Pfad.
    # Damit bekam ausgerechnet der Vertipper ein anderes Verhalten als der
    # Nicht-Konfigurierer. Wer den XML-Pfad will, setzt ihn ausdrücklich.
    _RAW_REPORT_TOOLCALL_MODE = os.environ.get('REPORT_TOOLCALL_MODE', 'native')
    _NORMALIZED_REPORT_TOOLCALL_MODE = _RAW_REPORT_TOOLCALL_MODE.strip().lower()
    if _NORMALIZED_REPORT_TOOLCALL_MODE not in ('native', 'xml'):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Invalid REPORT_TOOLCALL_MODE=%r — falling back to default 'native'",
            _RAW_REPORT_TOOLCALL_MODE,
        )
        _NORMALIZED_REPORT_TOOLCALL_MODE = 'native'
    REPORT_TOOLCALL_MODE: str = _NORMALIZED_REPORT_TOOLCALL_MODE

    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    # Issue #1303 — Panel-Rotation fuer Abschnitts-Interviews: eine Persona
    # wird pro Report-Lauf maximal so oft interviewt; neue Abschnitte ziehen
    # bevorzugt noch nicht befragte Personas, Wiederverwendung braucht einen
    # signifikant anderen Aspekt (siehe services/interview_panel.py).
    # 0 oder negativ schaltet die Rotation ab.
    REPORT_INTERVIEW_MAX_PER_PERSONA = int(
        os.environ.get('REPORT_INTERVIEW_MAX_PER_PERSONA', '2')
    )
    # Issue #1302 — maschinelle Vollständigkeitprüfung vor dem Report-
    # Abschluss: der Requirement-Checker (services/report_agent/
    # requirement_checker.py) prüft den fertigen Berichtstext gegen eine
    # konfigurierbare Checkliste und stuft fehlende Aspekte über die
    # bestehende run_degradations-Mechanik auf INCOMPLETE ab.
    REPORT_REQUIREMENT_CHECKER_ENABLED = os.environ.get(
        'REPORT_REQUIREMENT_CHECKER_ENABLED', 'true'
    ).strip().lower() in ('1', 'true', 'yes', 'on')
    # Output language for generated reports (plan, sections, chat answers).
    REPORT_LANGUAGE = os.environ.get('REPORT_LANGUAGE', 'German')

    # Default agent simulation language — controls in which language OASIS agents post and reply.
    # 'de' (Deutsch / Default) or 'en' (English). Per-simulation override possible via API.
    AGENT_LANGUAGE = os.environ.get('AGENT_LANGUAGE', 'de').lower()

    # Default social activity timing profile.
    TIME_PROFILE = os.environ.get('TIME_PROFILE', 'dach_default').lower()

    # Logging format: "text" (default, human-readable) or "json" (structured, machine-readable).
    # Mirrors the AGORA_LOG_FORMAT env var read directly in utils/logger.py at import time.
    AGORA_LOG_FORMAT = os.environ.get('AGORA_LOG_FORMAT', 'text').lower()

    # App-level abuse guard for short-lived signed ticket issuance.
    # Values <= 0 disable the limiter for local experiments/tests.
    AGORA_TICKET_RATE_LIMIT_MAX = int(os.environ.get('AGORA_TICKET_RATE_LIMIT_MAX', '60'))
    AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_UPLOAD_RATE_LIMIT_MAX = int(os.environ.get('AGORA_UPLOAD_RATE_LIMIT_MAX', '10'))
    AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    # Per-file upload cap for the ontology endpoint. Documents above this are
    # rejected with HTTP 413 before the request body is persisted to disk.
    AGORA_MAX_UPLOAD_SIZE_MB = int(os.environ.get('AGORA_MAX_UPLOAD_SIZE_MB', '50'))
    AGORA_LLM_TRIGGER_RATE_LIMIT_MAX = int(
        os.environ.get('AGORA_LLM_TRIGGER_RATE_LIMIT_MAX', '20')
    )
    AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_REPORT_RATE_LIMIT_MAX = int(os.environ.get('AGORA_REPORT_RATE_LIMIT_MAX', '10'))
    AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    # Workspace-Bootstrap und Mitgliederverwaltung (#1616).
    AGORA_WORKSPACE_RATE_LIMIT_MAX = int(os.environ.get('AGORA_WORKSPACE_RATE_LIMIT_MAX', '30'))
    AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_PROXY_FIX_X_FOR = int(os.environ.get('AGORA_PROXY_FIX_X_FOR', '0'))
    AGORA_PROXY_FIX_X_PROTO = int(os.environ.get('AGORA_PROXY_FIX_X_PROTO', '0'))
    AGORA_PROXY_FIX_X_HOST = int(os.environ.get('AGORA_PROXY_FIX_X_HOST', '0'))
    AGORA_PROXY_FIX_X_PORT = int(os.environ.get('AGORA_PROXY_FIX_X_PORT', '0'))
    AGORA_PROXY_FIX_X_PREFIX = int(os.environ.get('AGORA_PROXY_FIX_X_PREFIX', '0'))

    # Startup-Reconciliation (Tech-Review 2026-09-07 Slice B1): nach einem
    # Container-Restart markiert ``reconcile_stale_runs`` verwaiste Runs
    # (RunRegistry-Status pending/processing, deren Subprozess-PID tot ist
    # oder fehlt) als failed/process_restart, statt sie für immer als
    # "laufend" auszuweisen. Default an; für Tests/Debugging abschaltbar.
    AGORA_STARTUP_RECONCILIATION = (
        os.environ.get('AGORA_STARTUP_RECONCILIATION', 'true').lower() in ('true', '1', 'yes')
    )

    # Job-Lease mit Heartbeat und TTL (Issue #1472, Architekturentscheidung
    # 2026-09-24): ersetzt den alten PID+Token-Stempel ohne Ablauf. Das
    # Heartbeat-Intervall liegt bewusst deutlich unter der TTL (hier: 4.5x),
    # damit ein einzelner verpasster Heartbeat (Gevent-Jitter, GC-Pause,
    # kurzzeitige Registry-Contention) nicht sofort zum faelschlichen
    # "verwaist" fuehrt. Defaults spiegeln
    # ``app.contracts.job_lease_contract.DEFAULT_LEASE_TTL_S`` /
    # ``DEFAULT_HEARTBEAT_INTERVAL_S`` (bewusst als Literal dupliziert,
    # ``config.py`` haengt nicht von ``contracts/`` ab).
    AGORA_JOB_LEASE_TTL_SECONDS = int(os.environ.get('AGORA_JOB_LEASE_TTL_SECONDS', '90'))
    AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS = int(
        os.environ.get('AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS', '20')
    )
    # Obergrenze ohne Fortschritt (Codex-P1, PR #1555): meldet ein Job so
    # lange kein neues Run-Event, bleibt der Heartbeat aus und die Lease
    # verfaellt eine TTL spaeter. Weit ueber der TTL, damit ein einzelner
    # langer LLM-Call ohne Zwischenmeldung nicht als Haenger gilt.
    AGORA_JOB_LEASE_MAX_STALL_SECONDS = int(
        os.environ.get('AGORA_JOB_LEASE_MAX_STALL_SECONDS', '1800')
    )

    # Ontology mutation (Issue #11) — how to handle novel entity types that
    # the NER pipeline flags during simulation:
    #   disabled (default) → drop the signal, ontology never changes
    #   review_only        → audit-log only, no ontology write
    #   auto               → apply patches whose confidence clears
    #                        ONTOLOGY_MUTATION_MIN_CONFIDENCE
    ONTOLOGY_MUTATION_MODE = os.environ.get('ONTOLOGY_MUTATION_MODE', 'disabled').lower()
    ONTOLOGY_MUTATION_MIN_CONFIDENCE = float(
        os.environ.get('ONTOLOGY_MUTATION_MIN_CONFIDENCE', '0.6')
    )

    # Persona review (Slice 2.1) — when enabled, every persona carries a
    # ``review_status`` (pending/approved/rejected) that the upcoming
    # simulation-start gate (Slice 2.3) will enforce. While disabled, the
    # review service still works for clients that opt in explicitly, but no
    # gates are applied and the field is left absent from new personas.
    PERSONA_REVIEW_ENABLED = (
        os.environ.get('PERSONA_REVIEW_ENABLED', 'false').lower() == 'true'
    )

    # Slice 5.2 (Issue #1323): Rollenwechsel-Markierung beim Lesen der
    # actions.jsonl. Aus → keine Prüfung, role_conflict bleibt None.
    AGORA_ROLE_LEAKAGE_MARKING = (
        os.environ.get('AGORA_ROLE_LEAKAGE_MARKING', 'true').lower() in ('true', '1', 'yes')
    )

    # Event bus transport for simulation IPC (Issue #9 Phase B).
    # "redis" → RedisEventBus via REDIS_URL; "file" → FilePollingEventBus (offline fallback);
    # "auto" (default) → redis if REDIS_URL pings OK, otherwise file.
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    EVENT_BUS_BACKEND = os.environ.get('EVENT_BUS_BACKEND', 'auto').lower()

    # Curated LLM model presets shown in the UI dropdown alongside locally installed Ollama models.
    #
    # Issue #1290: die Eintraege tragen KEIN ``label`` mehr. Ein hier
    # hinterlegter Anzeigetext liefe am ``vue-i18n``-Katalog vorbei — das
    # Frontend koennte ihn weder uebersetzen noch an die aktive Locale
    # anpassen. Stattdessen liefert der Vertrag mit ``label_key`` einen
    # stabilen, sprachneutralen i18n-Schluessel; der Anzeigetext lebt in
    # ``frontend/src/i18n/locales/{de,en}.json`` unter ``llm.preset.*``.
    # ``name`` bleibt der Fallback, wenn ein Schluessel fehlt.
    #
    # Schluessel-Schema: ``llm.preset.<kind>.<slug>`` — ``slug`` ist der
    # Modellname ohne Vendor-Praefix, kleingeschrieben, jede Nicht-Alphanumerik
    # zu ``_``. ``tests/api/test_model_preset_label_keys.py`` haelt Schema,
    # Eindeutigkeit und die Deckung in beiden Locale-Dateien fest.
    LLM_MODEL_PRESETS = [
        {"name": "qwen3-coder-next:cloud", "label_key": "llm.preset.cloud.qwen3_coder_next", "kind": "cloud"},
        {"name": "qwen2.5:32b", "label_key": "llm.preset.ollama.qwen2_5_32b", "kind": "ollama"},
        {"name": "qwen2.5:14b", "label_key": "llm.preset.ollama.qwen2_5_14b", "kind": "ollama"},
        {"name": "llama3.1:8b", "label_key": "llm.preset.ollama.llama3_1_8b", "kind": "ollama"},
        {"name": "gpt-oss:20b", "label_key": "llm.preset.ollama.gpt_oss_20b", "kind": "ollama"},
        # Issue #1282 — Amazon Bedrock via OpenAI-kompatibler mantle-Pfad.
        # Auth via AWS_BEARER_TOKEN_BEDROCK, kein boto3/SigV4.
        # REGIONSGEBUNDEN und CHAT-VERIFIZIERT: jede ID ist am 2026-08-13 mit
        # einem echten ``POST /v1/chat/completions`` gegen die Default-Region
        # eu-central-1 geprueft worden. Katalog-Praesenz allein genuegt nicht —
        # der mantle-Pfad fuehrt Modelle, die diese Route ablehnen (die
        # gesamte ``anthropic.*``-Familie und alle ``openai.gpt-5.x``; die
        # brauchen die native Converse-API mit SigV4). Liste, Default-Region
        # und die ``fallback_models`` in ``llm_provider_registry.py`` werden
        # gemeinsam gepflegt; ``tests/llm/test_bedrock_model_catalog.py``
        # haelt sie deckungsgleich und probt sie gegen den Live-Endpunkt.
        {"name": "openai.gpt-oss-120b", "label_key": "llm.preset.bedrock.gpt_oss_120b", "kind": "bedrock"},
        {"name": "qwen.qwen3-235b-a22b-2507", "label_key": "llm.preset.bedrock.qwen3_235b_a22b_2507", "kind": "bedrock"},
        {"name": "minimax.minimax-m2.5", "label_key": "llm.preset.bedrock.minimax_m2_5", "kind": "bedrock"},
        {"name": "mistral.devstral-2-123b", "label_key": "llm.preset.bedrock.devstral_2_123b", "kind": "bedrock"},
        {"name": "nvidia.nemotron-super-3-120b", "label_key": "llm.preset.bedrock.nemotron_super_3_120b", "kind": "bedrock"},
        {"name": "zai.glm-4.7-flash", "label_key": "llm.preset.bedrock.glm_4_7_flash", "kind": "bedrock"},
    ]

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        from .utils.logger import get_logger
        logger = get_logger('agora.config')

        errors = []
        secret_key_value = (cls.SECRET_KEY or '').strip()
        if not secret_key_value:
            if cls.DEBUG:
                import secrets
                cls.SECRET_KEY = secrets.token_urlsafe(32)
                logger.warning("SECRET_KEY not set — generated ephemeral dev key.")
            else:
                errors.append("SECRET_KEY not configured (required when FLASK_DEBUG is false)")
        elif not cls.DEBUG and secret_key_value.lower() in SECRET_KEY_PLACEHOLDERS:
            errors.append(
                "SECRET_KEY uses a known placeholder value — generate a real "
                "secret with `python -c \"import secrets; print(secrets.token_urlsafe(32))\"` "
                "(required when FLASK_DEBUG is false)"
            )
        elif cls.DEBUG and secret_key_value.lower() in SECRET_KEY_PLACEHOLDERS:
            logger.warning(
                "SECRET_KEY uses a placeholder value (%s). Acceptable in debug only.",
                secret_key_value,
            )
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY not configured (set to any non-empty value, e.g. 'ollama')")
        if not cls.NEO4J_URI:
            errors.append("NEO4J_URI not configured")
        neo4j_password_value = (cls.NEO4J_PASSWORD or '').strip()
        if not neo4j_password_value:
            errors.append("NEO4J_PASSWORD not configured")
        elif not cls.DEBUG and neo4j_password_value.lower() in NEO4J_PASSWORD_PLACEHOLDERS:
            errors.append(
                "NEO4J_PASSWORD uses a known placeholder value — set a real "
                "password (required when FLASK_DEBUG is false)"
            )
        elif cls.DEBUG and neo4j_password_value.lower() in NEO4J_PASSWORD_PLACEHOLDERS:
            logger.warning(
                "NEO4J_PASSWORD uses a placeholder value. Acceptable in debug only.",
            )

        # Auth-Policy: außerhalb FLASK_DEBUG entweder ein Token oder eine
        # bewusste Opt-out-Entscheidung.
        errors.extend(validate_master_token_policy(cls.DEBUG, cls.AUTH_BACKEND))

        # PostgreSQL-Grundlage (docs/plans/supabase.md §8).
        errors.extend(validate_database_settings(cls.METADATA_BACKEND, cls.DATABASE_URL))
        # Ablage der LLM-Profile (§10, PR 3).
        errors.extend(validate_llm_profile_backend(cls.LLM_PROFILE_BACKEND))
        # Ablage der Projekt-Metadaten (§11, PR 6).
        errors.extend(
            validate_project_backend(cls.PROJECT_BACKEND, cls.DATABASE_URL)
        )
        errors.extend(
            validate_simulation_backend(
                cls.SIMULATION_BACKEND, cls.DATABASE_URL, cls.PROJECT_BACKEND
            )
        )
        errors.extend(
            validate_run_backend(
                cls.RUN_BACKEND, cls.DATABASE_URL, cls.SIMULATION_BACKEND
            )
        )
        errors.extend(
            validate_report_backend(
                cls.REPORT_BACKEND, cls.DATABASE_URL, cls.SIMULATION_BACKEND
            )
        )
        # Auth-Modus und Supabase-JWT (ADR-0018).
        errors.extend(validate_auth_backend(cls))
        # Decision-Layer-Pilotierung (f005, ADR-0016).
        errors.extend(validate_decision_layer_mode(cls.DECISION_LAYER_MODE))
        # Job-Lease (Issue #1472).
        errors.extend(
            validate_job_lease_timing(
                cls.AGORA_JOB_LEASE_TTL_SECONDS,
                cls.AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS,
                cls.AGORA_JOB_LEASE_MAX_STALL_SECONDS,
            )
        )

        expected_dim = infer_vector_dim_for_model(cls.EMBEDDING_MODEL)
        if expected_dim and cls.VECTOR_DIM != expected_dim:
            errors.append(
                "VECTOR_DIM mismatch for EMBEDDING_MODEL "
                f"'{cls.EMBEDDING_MODEL}': configured {cls.VECTOR_DIM}, expected {expected_dim}"
            )
        return errors
