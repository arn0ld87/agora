"""
Configuration Management
Loads configuration from .env file in project root directory
"""

import os
from dotenv import load_dotenv

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

import importlib  # noqa: E402
from . import _config_groups, _config_validators  # noqa: E402

importlib.reload(_config_validators)
importlib.reload(_config_groups)

from ._config_validators import (  # noqa: E402
    AUTH_BACKENDS,
    DATABASE_URL_PREFIX,
    DEMO_MODE_FORBIDDEN_ENV_VARS,
    LLM_PROFILE_BACKENDS,
    LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE,
    METADATA_BACKENDS,
    NEO4J_PASSWORD_PLACEHOLDERS,
    PERSONA_SET_BACKENDS,
    PROJECT_BACKENDS,
    PROJECT_BACKENDS_NOT_YET_AVAILABLE,
    REPORT_BACKENDS,
    RUN_BACKENDS,
    SECRET_KEY_PLACEHOLDERS,
    SIMULATION_BACKENDS,
    TENANT_ISOLATION_AVAILABLE,
    WORKSPACE_SCOPED_BACKENDS,
    _tenant_isolation_errors,
    demo_mode_leaked_operator_vars,
    is_demo_mode,
    supabase_jwt_configured,
    supabase_jwt_settings,
    validate_auth_backend,
    validate_database_settings,
    validate_llm_profile_backend,
    validate_master_token_policy,
    validate_persona_set_backend,
    validate_project_backend,
    validate_report_backend,
    validate_run_backend,
    validate_simulation_backend,
)
from ._config_groups import (  # noqa: E402
    DECISION_LAYER_MODES,
    KNOWN_EMBEDDING_DIMS,
    BackendsConfigMixin,
    DomainConfigMixin,
    FlaskCoreConfigMixin,
    _env_ratio,
    infer_vector_dim_for_model,
    validate_decision_layer_mode,
    validate_job_lease_timing,
)


class Config(
    FlaskCoreConfigMixin,
    BackendsConfigMixin,
    DomainConfigMixin,
):
    """Flask configuration class"""

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
        # Im Demo-Modus kommen LLM-Keys ausschliesslich aus den Workspace-
        # Connections (BYOK); ein Betreiber-LLM_API_KEY ist dort sogar verboten
        # (DEMO_MODE_FORBIDDEN_ENV_VARS).
        if not cls.LLM_API_KEY and not is_demo_mode():
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
        errors.extend(
            validate_persona_set_backend(cls.PERSONA_SET_BACKEND, cls.DATABASE_URL)
        )
        # Auth-Modus und Supabase-JWT (ADR-0018).
        errors.extend(validate_auth_backend(cls))
        # Decision-Layer-Pilotierung (f005, ADR-0016).
        errors.extend(validate_decision_layer_mode(cls.DECISION_LAYER_MODE))
        if not (0 < cls.JEV_TIMEOUT_S <= 30):
            errors.append(
                f"AGORA_JEV_TIMEOUT_S must be > 0 and <= 30 (got {cls.JEV_TIMEOUT_S})"
            )
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


__all__ = [
    'AUTH_BACKENDS',
    'Config',
    'DATABASE_URL_PREFIX',
    'DECISION_LAYER_MODES',
    'DEMO_MODE_FORBIDDEN_ENV_VARS',
    'KNOWN_EMBEDDING_DIMS',
    'LLM_PROFILE_BACKENDS',
    'LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE',
    'METADATA_BACKENDS',
    'NEO4J_PASSWORD_PLACEHOLDERS',
    'PERSONA_SET_BACKENDS',
    'PROJECT_BACKENDS',
    'PROJECT_BACKENDS_NOT_YET_AVAILABLE',
    'REPORT_BACKENDS',
    'RUN_BACKENDS',
    'SECRET_KEY_PLACEHOLDERS',
    'SIMULATION_BACKENDS',
    'TENANT_ISOLATION_AVAILABLE',
    'WORKSPACE_SCOPED_BACKENDS',
    '_env_ratio',
    '_tenant_isolation_errors',
    'demo_mode_leaked_operator_vars',
    'infer_vector_dim_for_model',
    'is_demo_mode',
    'project_root_env',
    'supabase_jwt_configured',
    'supabase_jwt_settings',
    'validate_auth_backend',
    'validate_database_settings',
    'validate_decision_layer_mode',
    'validate_job_lease_timing',
    'validate_llm_profile_backend',
    'validate_master_token_policy',
    'validate_persona_set_backend',
    'validate_project_backend',
    'validate_report_backend',
    'validate_run_backend',
    'validate_simulation_backend',
]
