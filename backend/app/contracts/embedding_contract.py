"""Canonical embedding provider and configuration contracts (Onboarding Slice 4.1).

ADR-0009 (geplant, vgl. ``docs/epics/onboarding-provider-unification/03-target-architecture.md``):
``EmbeddingConfiguration``, ``EmbeddingMigrationJob`` und ``EmbeddingIndexVersion``
werden Pydantic-v2-Single-Source-of-Truth. Sie sind strikt getrennt von der
Chat-Routing-Welt (``ProviderConnection``, ``AiModel``, ``AiRoute`` aus
``ai_provider_contract.py``) — Embedding- und Chat-Pfade teilen sich nur die
Provider-Verbindung als Referenz, niemals das Modell.

Bestehende ``Config.EMBEDDING_*``-Werte bleiben ueber einen schmalen Adapter
lesbar, der in Slice 4.2 ergaenzt wird. Bis dahin validiert dieser Vertrag nur
die kanonische Struktur.

Wichtige Invarianten:

* ``EmbeddingConfiguration.provider_kind`` ist eine echte **Restriktion** der
  bestehenden ``ProviderConnectionKind``-Menge — Anthropic und CLI-Bridges
  bleiben ausgeschlossen, weil sie keine Embeddings anbieten.
* ``EmbeddingConfiguration.dimensions`` ist nach ``probed`` und nach jeder
  Re-Embedding-Migration **verifiziert**; der Vertrag akzeptiert nur
  ``int > 0``.
* ``EmbeddingConfiguration.index_version`` verweist auf einen versionierten
  Neo4j-Vector-Index; das ermoeglicht parallele Indizes waehrend der
  Re-Embedding-Migration (siehe Migrations-Plan 06-migration-plan.md).
* ``scope="project"`` verlangt eine ``project_id``; ``scope="global"`` darf
  keine haben. Damit ist die Per-Project-Snapshot-Anforderung strukturell
  abgesichert.
* ``EmbeddingMigrationJob`` ist der vollstaendige Lifecycle-Vertrag fuer die
  Re-Embedding-Migration mit Checkpoint, Fortschritt, Abbruch und Fehler.
* ``EmbeddingIndexVersion`` dokumentiert pro Version, welches Modell und welche
  Property genutzt wurden — so kann ein alter Index nach erfolgreicher
  Migration explizit als ``superseded`` markiert werden, ohne dass die
  Embedding-Property ploetzlich verschwindet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provider_types import ProviderConnectionKind

_STRICT = ConfigDict(extra="forbid")

# ----------------------------------------------------------------------
# Sub-Restriktion: Welche ProviderConnectionKind-Werte duerfen als
# Embedding-Quelle dienen? Anthropic, OpenCode Go und CLI-Bridges sind
# bewusst ausgeschlossen.
# ----------------------------------------------------------------------

_EMBEDDING_PROVIDER_KINDS: frozenset[str] = frozenset(
    {
        "ollama",
        "openai",
        "google",
        "custom",
        "ollama_cloud",
        "openai_compatible",
    }
)

EmbeddingProviderKind = Literal[
    "ollama",
    "openai",
    "google",
    "custom",
    "ollama_cloud",
    "openai_compatible",
]

# Konfigurationsstatus. Proposed -> Probed -> (Reembedding | Active) -> ...
# (siehe 03-target-architecture.md, "Embedding-Lifecycle").
EmbeddingConfigurationStatus = Literal[
    "proposed",       # Modell gewaehlt, noch nicht verifiziert
    "probed",         # Test-Embedding hat die verlangte Dimension bestaetigt
    "reembedding",    # Re-Embedding-Migration laeuft, alter Index noch aktiv
    "validated",      # Migration abgeschlossen, noch nicht auf neuen Index umgeschaltet
    "active",         # aktiver Standard-Embedding-Provider
    "rolled_back",    # Operator hat auf alten Index zurueckgeschaltet
    "failed",         # Konfiguration dauerhaft ungueltig
]

# Konfigurations-Scope. ``global`` = Workspace-Default, ``project`` = pro
# Projekt ueberschrieben. Per-Project-Snapshots sind im Migrations-Plan
# explizit gefordert ("Speichere die Embedding-Konfiguration als Snapshot
# pro Projekt bzw. Graph").
EmbeddingConfigurationScope = Literal["global", "project"]

# Lifecycle der Re-Embedding-Migration.
EmbeddingMigrationStatus = Literal[
    "pending",        # Job angelegt, noch nicht gestartet
    "running",        # Re-Embedding laeuft, alter Index aktiv
    "validating",     # Anzahl/Dimension/Stichprobe wird geprueft
    "completed",      # Validierung ok, atomarer Switch steht aus
    "rolled_back",    # Operator hat den Job abgebrochen / zurueckgerollt
    "failed",         # Job dauerhaft fehlgeschlagen
]

# Status eines versionierten Neo4j-Vector-Index.
EmbeddingIndexStatus = Literal[
    "active",         # wird aktuell fuer Vektor-Suche genutzt
    "superseded",     # durch eine neuere Version ersetzt, noch lesbar
    "rolled_back",    # Operator hat explizit zurueckgeschaltet
    "retired",        # explizit aus dem Verkehr gezogen
]


def embedding_provider_kinds() -> frozenset[str]:
    """Gibt die erlaubten ``ProviderConnectionKind``-Werte fuer Embedding-Configs zurueck.

    Wird von anderen Modulen (Service, API, Validierung) verwendet, um die
    Restriktion konsistent zu pruefen, ohne den Literal-Type explizit zu
    duplizieren.
    """
    return _EMBEDDING_PROVIDER_KINDS


class EmbeddingModelMetadata(BaseModel):
    """Metadaten zu einem Embedding-Modell, isoliert von Chat-Modellen.

    Slice 4.1 liefert nur die strukturelle Form. Die Live-Discovery
    (Capabilities, Live-Dimension, Modell-Katalog) ist Teil von Slice 4.2
    (Service) und Slice 4.3 (Anbieter-spezifische Adapter).
    """

    model_config = _STRICT

    provider_kind: EmbeddingProviderKind
    model_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    embedding_dimensions: int = Field(gt=0)
    source: Literal["live", "cached", "fallback", "custom"]
    deprecated: bool = False
    metadata_updated_at: datetime | None = None


class EmbeddingConfiguration(BaseModel):
    """Kanonische Embedding-Konfiguration (SSoT).

    Pro ``scope="global"`` darf es hoechstens eine ``active`` Konfiguration
    geben. Pro ``scope="project"`` ebenfalls hoechstens eine ``active`` pro
    ``project_id``. Diese Eindeutigkeit wird strukturell nicht erzwungen
    (sie wuerde einen Unique-Index in der Persistenz erfordern); sie ist
    Aufgabe des ``EmbeddingConfigurationService`` in Slice 4.2.
    """

    model_config = _STRICT

    id: str = Field(min_length=1)
    provider_connection_id: str = Field(min_length=1)
    provider_kind: EmbeddingProviderKind
    model_id: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    scope: EmbeddingConfigurationScope
    project_id: str | None = None
    index_version: int = Field(ge=1)
    status: EmbeddingConfigurationStatus = "proposed"
    status_message: str | None = None
    created_at: datetime
    updated_at: datetime
    last_validated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scope_and_project(self) -> EmbeddingConfiguration:
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope='project'")
        if self.scope == "global" and self.project_id is not None:
            raise ValueError("project_id must be None when scope='global'")
        return self

    @model_validator(mode="after")
    def validate_status_dimension_match(self) -> EmbeddingConfiguration:
        # ``probed`` und spaetere Status setzen verifizierte Dimension voraus.
        # ``proposed`` darf ebenfalls eine bekannte Dimension haben (statische
        # Lookup aus ``infer_vector_dim_for_model``), aber dann muss die
        # statische Quelle dokumentiert sein — der Vertrag akzeptiert beides
        # und ueberlaesst die Verifikation dem Service.
        if self.dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        return self


class EmbeddingConfigurationUpsertRequest(BaseModel):
    """Request-Vertrag fuer Anlegen/Aktualisieren einer Embedding-Konfiguration.

    Wie bei ``ProviderConnectionUpsertRequest``: API-Keys werden nicht im
    Vertrag transportiert, sondern ausschliesslich ueber den
    ``provider_connection_id`` referenziert (Secret-Store entkoppelt).
    """

    model_config = _STRICT

    provider_connection_id: str = Field(min_length=1)
    provider_kind: EmbeddingProviderKind
    model_id: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    scope: EmbeddingConfigurationScope
    project_id: str | None = None

    @model_validator(mode="after")
    def validate_scope_and_project(self) -> EmbeddingConfigurationUpsertRequest:
        if self.scope == "project" and not self.project_id:
            raise ValueError("project_id is required when scope='project'")
        if self.scope == "global" and self.project_id is not None:
            raise ValueError("project_id must be None when scope='global'")
        return self


class EmbeddingConfigurationResponse(BaseModel):
    """Antwort-Wrapper analog zu ``ProviderConnectionResponse``."""

    model_config = _STRICT

    configuration: EmbeddingConfiguration


class EmbeddingMigrationProgress(BaseModel):
    """Fortschritt einer Re-Embedding-Migration.

    ``processed`` + ``failed`` <= ``total``. Die Konsistenz wird im Service
    erzwungen, nicht im Vertrag, weil der Vertrag sonst Transienten
    ausgesetzt waere (running -> Progress kann temporaer inkonsistent sein).
    """

    model_config = _STRICT

    total: int = Field(ge=0)
    processed: int = Field(ge=0)
    failed: int = Field(ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class EmbeddingMigrationJob(BaseModel):
    """Lifecycle einer Re-Embedding-Migration.

    Ein Job schliesst die Luecke zwischen zwei ``EmbeddingIndexVersion``-Werten:
    Der ``source_index_version`` bleibt aktiv, waehrend ``target_index_version``
    befuellt wird. Erst nach erfolgreicher Validierung schaltet der
    ``EmbeddingConfigurationService`` den Alias um (siehe 03-target-architecture.md
    "Embedding-Lifecycle").
    """

    model_config = _STRICT

    id: str = Field(min_length=1)
    configuration_id: str = Field(min_length=1)
    source_index_version: int = Field(ge=1)
    target_index_version: int = Field(ge=1)
    status: EmbeddingMigrationStatus = "pending"
    progress: EmbeddingMigrationProgress
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_versions_differ(self) -> EmbeddingMigrationJob:
        if self.source_index_version == self.target_index_version:
            raise ValueError(
                "source_index_version and target_index_version must differ"
            )
        return self


class EmbeddingMigrationJobResponse(BaseModel):
    """Antwort-Wrapper fuer einen Migrations-Job."""

    model_config = _STRICT

    job: EmbeddingMigrationJob


class EmbeddingIndexVersion(BaseModel):
    """Beschreibung einer einzelnen Version des Neo4j-Vector-Index.

    Pro Version existiert ein eigener ``index_name`` und ein eigener
    ``property_key`` auf den Graph-Knoten. Dadurch koennen mehrere Versionen
    parallel existieren, ohne dass die Embedding-Property ploetzlich
    verschwindet (vgl. 00-research Punkt 4 und 06-migration-plan.md).
    """

    model_config = _STRICT

    version: int = Field(ge=1)
    provider_connection_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    index_name: str = Field(min_length=1)
    property_key: str = Field(min_length=1)
    status: EmbeddingIndexStatus = "active"
    created_at: datetime
    retired_at: datetime | None = None

    @model_validator(mode="after")
    def validate_status_with_retired(self) -> EmbeddingIndexVersion:
        if self.status == "retired" and self.retired_at is None:
            raise ValueError("retired_at is required when status='retired'")
        return self


# ----------------------------------------------------------------------
# Helpers: Konsistenz mit dem Provider-Connection-Literal
# ----------------------------------------------------------------------


def provider_kind_supports_embeddings(kind: ProviderConnectionKind) -> bool:
    """Prueft, ob ein ``ProviderConnectionKind`` als Embedding-Quelle erlaubt ist.

    Wird vom Service verwendet, um eine ``ProviderConnection`` mit ihrer
    Embedding-Configuration zu verheiraten. Diese Funktion ist die Bruecke
    zwischen Slice 3 (ProviderConnection) und Slice 4 (EmbeddingConfiguration).
    """
    return kind in _EMBEDDING_PROVIDER_KINDS


__all__ = [
    "EmbeddingProviderKind",
    "EmbeddingConfigurationStatus",
    "EmbeddingConfigurationScope",
    "EmbeddingMigrationStatus",
    "EmbeddingIndexStatus",
    "EmbeddingModelMetadata",
    "EmbeddingConfiguration",
    "EmbeddingConfigurationUpsertRequest",
    "EmbeddingConfigurationResponse",
    "EmbeddingMigrationProgress",
    "EmbeddingMigrationJob",
    "EmbeddingMigrationJobResponse",
    "EmbeddingIndexVersion",
    "embedding_provider_kinds",
    "provider_kind_supports_embeddings",
]
