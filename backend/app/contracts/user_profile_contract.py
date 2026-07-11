"""Canonical user profile and onboarding state contracts (Onboarding Slice 2).

ADR-0008: Agora ist ein Single-User-System. ``UserProfile`` beschreibt die
lokale Person und ihre Einstellungen — es ist ausdruecklich KEIN KI-Preset
(``LlmProfile``). Beide leben in getrennten Schluesselraeumen und werden
nicht vermischt.

``OnboardingState`` ist der backendseitig persistierte, resumierbare Zustand
des Erst-Onboardings. Jeder Schritt wird nach Abschluss gespeichert; Abbruch
(``dismissed``) ist erlaubt und sperrt niemanden aus — Bestandsinstallationen
koennen den Wizard jederzeit wegklicken und spaeter ueber die Einstellungen
erneut oeffnen.

Fachliche Completion (Profil gueltig + mindestens ein Chat-Modell + gueltige
Embedding-Konfiguration, ADR-0008) wird serverseitig im Service geprueft;
der Contract sichert nur die strukturelle Schritt-Konsistenz.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_STRICT = ConfigDict(extra="forbid")

ProfileLanguage = Literal["de", "en"]
ProfileTheme = Literal["system", "light", "dark"]
PrivacyMode = Literal["standard", "strict"]
OperatingMode = Literal["local", "hybrid", "server"]
OnboardingStatus = Literal["not_started", "in_progress", "dismissed", "completed"]
OnboardingStepId = Literal[
    "welcome",
    "profile",
    "providers",
    "chat_model",
    "embeddings",
    "privacy",
    "summary",
]

# Kanonische Schritt-Reihenfolge des Wizards. Slice 2 liefert das Grundgeruest;
# die Schritte providers/chat_model/embeddings werden in Slice 3/4 funktional
# und zeigen bis dahin den realen Systemzustand (keine Attrappen).
ONBOARDING_STEP_ORDER: tuple[OnboardingStepId, ...] = (
    "welcome",
    "profile",
    "providers",
    "chat_model",
    "embeddings",
    "privacy",
    "summary",
)

# Schritte, ohne die ein Onboarding nicht als "completed" gelten darf.
REQUIRED_ONBOARDING_STEPS: frozenset[OnboardingStepId] = frozenset(
    {"profile", "chat_model", "embeddings"}
)

# Avatar-Upload-Grenzen (SVG ist bewusst NICHT erlaubt — Script-Injection).
ALLOWED_AVATAR_MIME_TYPES: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
MAX_AVATAR_BYTES: int = 2 * 1024 * 1024

# Referenz auf eine serverseitig generierte Avatar-Datei. Das strikte Pattern
# schliesst Path-Traversal und Fremdnamen bereits im Vertrag aus.
_AVATAR_REF_PATTERN = r"^avatar-[0-9a-f]{32}\.(png|jpg|webp)$"
AvatarRef = Annotated[str, Field(pattern=_AVATAR_REF_PATTERN)]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA timezone: {value!r}") from exc
    return value


IanaTimezone = Annotated[str, AfterValidator(_validate_timezone)]


class UserProfile(BaseModel):
    """Lokales Single-User-Profil (kein KI-Preset, keine Secrets)."""

    model_config = _STRICT

    avatar_ref: AvatarRef | None = None
    display_name: str = Field(min_length=1, max_length=80)
    username: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{1,31}$"
    )
    role: str | None = Field(default=None, max_length=120)
    organisation: str | None = Field(default=None, max_length=120)
    language: ProfileLanguage = "de"
    timezone: IanaTimezone = "Europe/Berlin"
    report_language: ProfileLanguage = "de"
    theme: ProfileTheme = "system"
    privacy_mode: PrivacyMode = "standard"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped


class UserProfileUpdateRequest(BaseModel):
    """Partielles Update; ``avatar_ref`` ist bewusst ausgeschlossen und wird
    ausschliesslich ueber die Avatar-Endpunkte veraendert."""

    model_config = _STRICT

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    username: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9._-]{1,31}$"
    )
    role: str | None = Field(default=None, max_length=120)
    organisation: str | None = Field(default=None, max_length=120)
    language: ProfileLanguage | None = None
    timezone: IanaTimezone | None = None
    report_language: ProfileLanguage | None = None
    theme: ProfileTheme | None = None
    privacy_mode: PrivacyMode | None = None

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("display_name must not be blank")
        return stripped


class OnboardingState(BaseModel):
    """Resumierbarer Wizard-Zustand; wird nach jedem Schritt persistiert."""

    model_config = _STRICT

    status: OnboardingStatus = "not_started"
    operating_mode: OperatingMode | None = None
    current_step: OnboardingStepId = "welcome"
    completed_steps: list[OnboardingStepId] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("completed_steps")
    @classmethod
    def _no_duplicate_steps(
        cls, value: list[OnboardingStepId]
    ) -> list[OnboardingStepId]:
        if len(value) != len(set(value)):
            raise ValueError("completed_steps must not contain duplicates")
        return value

    @model_validator(mode="after")
    def _completed_requires_required_steps(self) -> "OnboardingState":
        if self.status == "completed":
            missing = REQUIRED_ONBOARDING_STEPS - set(self.completed_steps)
            if missing:
                raise ValueError(
                    "completed onboarding requires steps: "
                    + ", ".join(sorted(missing))
                )
        return self


class OnboardingStepUpdateRequest(BaseModel):
    """Meldet einen abgeschlossenen Schritt; der Service berechnet den
    naechsten offenen Schritt deterministisch aus ``ONBOARDING_STEP_ORDER``."""

    model_config = _STRICT

    step: OnboardingStepId
    operating_mode: OperatingMode | None = None


class OnboardingRequirements(BaseModel):
    """Serverseitig berechnete Completion-Voraussetzungen (ADR-0008)."""

    model_config = _STRICT

    profile_valid: bool
    # "configured", nicht "available": ein Live-Erreichbarkeitscheck kommt
    # erst mit der Provider-Discovery in Slice 3.
    chat_model_configured: bool
    embedding_configured: bool


class OnboardingStatusResponse(BaseModel):
    """Antwort von ``GET /api/onboarding``."""

    model_config = _STRICT

    state: OnboardingState
    requirements: OnboardingRequirements
    onboarding_required: bool
