"""Prüfung von Supabase-Access-Tokens (ADR-0018, Plan §15, Issue #1613).

Flask vertraut einem Bearer-JWT nur, wenn **alle** Punkte aus §15 halten:
Signatur, ``iss``, ``aud``, ``exp``/``nbf`` und ein ``sub``, das eine UUID ist.
Was das Frontend sonst behauptet (Workspace, Rolle), zählt hier nicht — die
Mitgliedschaft prüft der Guard gegen ``agora.workspace_members``.

Zwei Schlüsselquellen, nie beide zugleich:

* ``AGORA_SUPABASE_JWKS_URL`` — asymmetrische Schlüssel (RS256/ES256) aus dem
  JWKS-Endpunkt von GoTrue, mit Cache.
* ``AGORA_SUPABASE_JWT_SECRET`` — gemeinsames HS256-Secret (Supabase-Default
  ``JWT_SECRET``).

Die Algorithmus-Allowlist hängt an der Quelle. Damit ist die klassische
Verwechslung ausgeschlossen, bei der ein Angreifer ein HS256-Token mit dem
öffentlichen RSA-Schlüssel als HMAC-Secret signiert; ``alg=none`` ist nie
erlaubt.

Die JWKS-URL ist Betreiberkonfiguration und zeigt typischerweise auf einen
internen Dienst. Sie läuft deshalb bewusst nicht über
:mod:`app.security.outbound_http`, dessen SSRF-Schutz für URLs aus
nicht-vertrauenswürdigen Quellen gedacht ist und interne Ziele ablehnt.

Weder Token noch Claims landen im Log; Fehler tragen nur einen Code.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

import jwt
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

#: Algorithmen je Schlüsselquelle. Asymmetrisch nur mit JWKS, HS256 nur mit
#: Secret — nie gemischt.
JWKS_ALGORITHMS: tuple[str, ...] = ('RS256', 'ES256')
SECRET_ALGORITHMS: tuple[str, ...] = ('HS256',)

#: Kürzeste Länge eines HS256-Secrets. Supabase verlangt selbst 32 Zeichen.
MIN_SECRET_LENGTH = 32


class JwtErrorCode(str, Enum):
    """Grund, aus dem ein Token abgelehnt wurde — ohne Token-Inhalt."""

    MALFORMED = 'malformed'
    UNSUPPORTED_ALGORITHM = 'unsupported_algorithm'
    INVALID_SIGNATURE = 'invalid_signature'
    EXPIRED = 'expired'
    NOT_YET_VALID = 'not_yet_valid'
    INVALID_ISSUER = 'invalid_issuer'
    INVALID_AUDIENCE = 'invalid_audience'
    MISSING_CLAIM = 'missing_claim'
    INVALID_SUBJECT = 'invalid_subject'
    ANONYMOUS_USER = 'anonymous_user'
    KEY_UNAVAILABLE = 'key_unavailable'


class JwtVerificationError(Exception):
    """Ein Token ist ungültig. ``code`` ist sicher loggbar, der Text auch."""

    def __init__(self, code: JwtErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class SupabaseJwtSettings(BaseModel):
    """Konfiguration der Prüfung. Genau eine Schlüsselquelle."""

    model_config = ConfigDict(frozen=True)

    issuer: str = Field(min_length=1)
    audience: str = Field(default='authenticated', min_length=1)
    jwks_url: str | None = None
    secret: SecretStr | None = None
    #: Toleranz für Uhrenabweichung zwischen GoTrue und Flask.
    leeway_seconds: int = Field(default=30, ge=0, le=300)
    #: Wie lange abgerufene JWKS-Schlüssel gelten.
    jwks_cache_seconds: int = Field(default=300, ge=30, le=86400)
    #: Timeout für den JWKS-Abruf.
    jwks_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    @model_validator(mode='after')
    def _exactly_one_key_source(self) -> 'SupabaseJwtSettings':
        has_jwks = bool((self.jwks_url or '').strip())
        has_secret = self.secret is not None and bool(
            self.secret.get_secret_value()
        )
        if has_jwks == has_secret:
            raise ValueError(
                'exactly one of AGORA_SUPABASE_JWKS_URL and '
                'AGORA_SUPABASE_JWT_SECRET must be set'
            )
        if has_secret and len(self.secret.get_secret_value()) < MIN_SECRET_LENGTH:  # type: ignore[union-attr]
            raise ValueError(
                f'AGORA_SUPABASE_JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters'
            )
        if has_jwks and not (self.jwks_url or '').startswith(('https://', 'http://')):
            raise ValueError('AGORA_SUPABASE_JWKS_URL must be an http(s) URL')
        return self

    @property
    def algorithms(self) -> tuple[str, ...]:
        return JWKS_ALGORITHMS if self.jwks_url else SECRET_ALGORITHMS


class SupabaseJwtClaims(BaseModel):
    """Die Claims, die Agora aus einem gültigen Token verwendet."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str | None = None
    session_id: str | None = None
    expires_at: int


_PYJWT_ERRORS: tuple[tuple[type[Exception], JwtErrorCode], ...] = (
    (jwt.ExpiredSignatureError, JwtErrorCode.EXPIRED),
    (jwt.ImmatureSignatureError, JwtErrorCode.NOT_YET_VALID),
    (jwt.InvalidIssuerError, JwtErrorCode.INVALID_ISSUER),
    (jwt.InvalidAudienceError, JwtErrorCode.INVALID_AUDIENCE),
    (jwt.MissingRequiredClaimError, JwtErrorCode.MISSING_CLAIM),
    (jwt.InvalidAlgorithmError, JwtErrorCode.UNSUPPORTED_ALGORITHM),
    (jwt.InvalidSignatureError, JwtErrorCode.INVALID_SIGNATURE),
    (jwt.DecodeError, JwtErrorCode.MALFORMED),
)


def looks_like_jwt(token: str) -> bool:
    """Drei Base64url-Segmente, beginnend mit einem JSON-Header.

    Trennt im Hybrid-Modus ein Bearer-JWT vom Master-Token und von
    ``ago_``-Keys, ohne zu dekodieren.
    """
    return token.count('.') == 2 and token.startswith('eyJ') and ' ' not in token


class SupabaseJwtVerifier:
    """Prüft Access-Tokens gegen :class:`SupabaseJwtSettings`."""

    def __init__(self, settings: SupabaseJwtSettings) -> None:
        self._settings = settings
        self._jwks_client: jwt.PyJWKClient | None = None
        if settings.jwks_url:
            # Nur der JWKS-Satz wird gecacht, mit Ablauf (``lifespan``).
            # ``cache_keys=True`` legte zusätzlich einen LRU-Cache je Schlüssel
            # ohne Ablauf an: ein rotierter oder kompromittierter Schlüssel
            # bliebe bis zum Neustart gültig (Codex-Review auf #1622).
            self._jwks_client = jwt.PyJWKClient(
                settings.jwks_url,
                cache_keys=False,
                cache_jwk_set=True,
                lifespan=settings.jwks_cache_seconds,
                timeout=settings.jwks_timeout_seconds,
            )

    @property
    def settings(self) -> SupabaseJwtSettings:
        return self._settings

    def _signing_key(self, token: str) -> Any:
        if self._jwks_client is None:
            assert self._settings.secret is not None
            return self._settings.secret.get_secret_value()
        try:
            return self._jwks_client.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientConnectionError as exc:
            raise JwtVerificationError(JwtErrorCode.KEY_UNAVAILABLE) from exc
        except jwt.PyJWKSetError as exc:
            # Leerer oder unbrauchbarer Schlüsselsatz: ein Problem des
            # Endpunkts, nicht des Tokens.
            raise JwtVerificationError(JwtErrorCode.KEY_UNAVAILABLE) from exc
        except jwt.PyJWKClientError as exc:
            # Unbekannte ``kid`` oder unbrauchbarer Schlüssel.
            raise JwtVerificationError(JwtErrorCode.INVALID_SIGNATURE) from exc
        except jwt.PyJWTError as exc:
            raise JwtVerificationError(JwtErrorCode.MALFORMED) from exc

    def verify(self, token: str) -> SupabaseJwtClaims:
        """Gibt die Claims zurück oder wirft :class:`JwtVerificationError`."""
        if not looks_like_jwt(token):
            raise JwtVerificationError(JwtErrorCode.MALFORMED)
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            # Auch ``InvalidTokenError`` (etwa eine numerische ``kid`` oder ein
            # unbekanntes ``crit``) ist ein kaputtes Token, kein 500
            # (Codex-Review auf #1622).
            raise JwtVerificationError(JwtErrorCode.MALFORMED) from exc
        # Vor jedem Schlüsselabruf: ein fremder Algorithmus (auch ``none``)
        # darf weder den JWKS-Endpunkt anstoßen noch bis zur Prüfung kommen.
        if header.get('alg') not in self._settings.algorithms:
            raise JwtVerificationError(JwtErrorCode.UNSUPPORTED_ALGORITHM)

        key = self._signing_key(token)
        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=list(self._settings.algorithms),
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                leeway=self._settings.leeway_seconds,
                options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
            )
        except jwt.PyJWTError as exc:
            for error_type, code in _PYJWT_ERRORS:
                if isinstance(exc, error_type):
                    raise JwtVerificationError(code) from exc
            raise JwtVerificationError(JwtErrorCode.MALFORMED) from exc

        if payload.get('is_anonymous') is True:
            # Anonyme Supabase-Sitzungen haben kein Konto und damit keine
            # Mitgliedschaft; ADR-0018 sieht sie nicht vor.
            raise JwtVerificationError(JwtErrorCode.ANONYMOUS_USER)
        try:
            user_id = UUID(str(payload['sub']))
        except ValueError as exc:
            raise JwtVerificationError(JwtErrorCode.INVALID_SUBJECT) from exc

        email = payload.get('email')
        session_id = payload.get('session_id')
        return SupabaseJwtClaims(
            user_id=user_id,
            email=email if isinstance(email, str) and email else None,
            session_id=session_id if isinstance(session_id, str) else None,
            expires_at=int(payload['exp']),
        )
