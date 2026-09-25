"""Prüfung von Supabase-Access-Tokens (ADR-0018, Plan §15, Issue #1613).

Jeder Punkt aus §15 hat einen eigenen Ablehnungsfall. Dazu die beiden
klassischen Angriffe auf JWT-Bibliotheken: ``alg=none`` und ein HS256-Token,
das mit dem öffentlichen RSA-Schlüssel als HMAC-Secret signiert ist.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.security.supabase_jwt import (
    JwtErrorCode,
    JwtVerificationError,
    SupabaseJwtSettings,
    SupabaseJwtVerifier,
    looks_like_jwt,
)

ISSUER = 'https://supabase.example.test/auth/v1'
SECRET = 'x' * 40
USER_ID = uuid.UUID('11111111-2222-4333-8444-555555555555')


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        'sub': str(USER_ID),
        'iss': ISSUER,
        'aud': 'authenticated',
        'iat': now,
        'exp': now + 600,
        'email': 'a@example.test',
        'session_id': 'sess-1',
        'role': 'authenticated',
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _hs_verifier() -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(SupabaseJwtSettings(issuer=ISSUER, secret=SECRET))


def _hs_token(**overrides: Any) -> str:
    return jwt.encode(_claims(**overrides), SECRET, algorithm='HS256')


def _reject(verifier: SupabaseJwtVerifier, token: str) -> JwtErrorCode:
    with pytest.raises(JwtVerificationError) as excinfo:
        verifier.verify(token)
    # Die Meldung ist nur der Code — kein Token-Inhalt.
    assert str(excinfo.value) == excinfo.value.code.value
    if token:
        assert token not in str(excinfo.value)
    return excinfo.value.code


# -- HS256 -------------------------------------------------------------------


def test_valid_token_yields_claims():
    claims = _hs_verifier().verify(_hs_token())

    assert claims.user_id == USER_ID
    assert claims.email == 'a@example.test'
    assert claims.session_id == 'sess-1'


@pytest.mark.parametrize(
    ('overrides', 'code'),
    [
        ({'exp': int(time.time()) - 3600}, JwtErrorCode.EXPIRED),
        ({'nbf': int(time.time()) + 3600}, JwtErrorCode.NOT_YET_VALID),
        ({'iss': 'https://evil.example.test/auth/v1'}, JwtErrorCode.INVALID_ISSUER),
        ({'aud': 'anon'}, JwtErrorCode.INVALID_AUDIENCE),
        ({'sub': None}, JwtErrorCode.MISSING_CLAIM),
        ({'iat': None}, JwtErrorCode.MISSING_CLAIM),
        ({'sub': 'kein-uuid'}, JwtErrorCode.INVALID_SUBJECT),
        ({'is_anonymous': True}, JwtErrorCode.ANONYMOUS_USER),
    ],
)
def test_each_section_15_check_rejects(overrides, code):
    assert _reject(_hs_verifier(), _hs_token(**overrides)) is code


def test_leeway_tolerates_small_clock_skew():
    token = _hs_token(exp=int(time.time()) - 10)

    assert _hs_verifier().verify(token).user_id == USER_ID


def test_wrong_secret_is_an_invalid_signature():
    token = jwt.encode(_claims(), 'y' * 40, algorithm='HS256')

    assert _reject(_hs_verifier(), token) is JwtErrorCode.INVALID_SIGNATURE


def test_alg_none_is_rejected():
    def seg(data: dict[str, Any]) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

    token = f"{seg({'alg': 'none', 'typ': 'JWT'})}.{seg(_claims())}."
    # Leere Signatur: das dritte Segment fehlt, looks_like_jwt reicht trotzdem.
    assert _reject(_hs_verifier(), token) in {
        JwtErrorCode.UNSUPPORTED_ALGORITHM,
        JwtErrorCode.MALFORMED,
    }
    padded = token + 'AAAA'
    assert _reject(_hs_verifier(), padded) is JwtErrorCode.UNSUPPORTED_ALGORITHM


def test_asymmetric_token_is_rejected_by_a_secret_verifier():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(_claims(), key, algorithm='RS256')

    assert _reject(_hs_verifier(), token) is JwtErrorCode.UNSUPPORTED_ALGORITHM


@pytest.mark.parametrize('token', ['', 'abc', 'ago_' + 'a' * 40, 'a.b', 'eyJ.a.b.c'])
def test_non_jwt_shapes_are_malformed(token):
    assert _reject(_hs_verifier(), token) is JwtErrorCode.MALFORMED


# -- JWKS (RS256) -------------------------------------------------------------


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks_verifier(rsa_key, monkeypatch):
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    jwk.update({'kid': 'key-1', 'use': 'sig', 'alg': 'RS256'})
    verifier = SupabaseJwtVerifier(
        SupabaseJwtSettings(
            issuer=ISSUER, jwks_url='http://auth.internal:9999/.well-known/jwks.json'
        )
    )
    assert verifier._jwks_client is not None
    monkeypatch.setattr(verifier._jwks_client, 'fetch_data', lambda: {'keys': [jwk]})
    return verifier


def test_rs256_token_from_jwks_is_valid(rsa_key, jwks_verifier):
    token = jwt.encode(_claims(), rsa_key, algorithm='RS256', headers={'kid': 'key-1'})

    assert jwks_verifier.verify(token).user_id == USER_ID


def test_unknown_kid_is_an_invalid_signature(rsa_key, jwks_verifier):
    token = jwt.encode(_claims(), rsa_key, algorithm='RS256', headers={'kid': 'fremd'})

    assert _reject(jwks_verifier, token) is JwtErrorCode.INVALID_SIGNATURE


def test_foreign_rsa_key_is_an_invalid_signature(jwks_verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(_claims(), other, algorithm='RS256', headers={'kid': 'key-1'})

    assert _reject(jwks_verifier, token) is JwtErrorCode.INVALID_SIGNATURE


def test_hs256_signed_with_public_key_is_rejected(rsa_key, jwks_verifier):
    """Algorithmus-Verwechslung: der öffentliche Schlüssel als HMAC-Secret."""
    public_pem = rsa_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    header = base64.urlsafe_b64encode(
        json.dumps({'alg': 'HS256', 'typ': 'JWT', 'kid': 'key-1'}).encode()
    ).rstrip(b'=')
    body = base64.urlsafe_b64encode(json.dumps(_claims()).encode()).rstrip(b'=')
    import hashlib
    import hmac

    sig = base64.urlsafe_b64encode(
        hmac.new(public_pem, header + b'.' + body, hashlib.sha256).digest()
    ).rstrip(b'=')
    token = b'.'.join([header, body, sig]).decode()

    assert _reject(jwks_verifier, token) is JwtErrorCode.UNSUPPORTED_ALGORITHM


def test_unreachable_jwks_is_key_unavailable(rsa_key, monkeypatch):
    verifier = SupabaseJwtVerifier(
        SupabaseJwtSettings(issuer=ISSUER, jwks_url='http://auth.internal:9999/jwks')
    )

    def boom():
        raise jwt.PyJWKClientConnectionError('down')

    assert verifier._jwks_client is not None
    monkeypatch.setattr(verifier._jwks_client, 'fetch_data', boom)
    token = jwt.encode(_claims(), rsa_key, algorithm='RS256', headers={'kid': 'key-1'})

    assert _reject(verifier, token) is JwtErrorCode.KEY_UNAVAILABLE


# -- Einstellungen --------------------------------------------------------------


@pytest.mark.parametrize(
    'kwargs',
    [
        {},
        {'secret': SECRET, 'jwks_url': 'https://a.test/jwks'},
        {'secret': 'zu-kurz'},
        {'jwks_url': 'file:///etc/passwd'},
    ],
)
def test_settings_need_exactly_one_valid_key_source(kwargs):
    with pytest.raises(ValidationError):
        SupabaseJwtSettings(issuer=ISSUER, **kwargs)


def test_settings_never_print_the_secret():
    settings = SupabaseJwtSettings(issuer=ISSUER, secret=SECRET)

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings.model_dump())


def test_algorithms_follow_the_key_source():
    assert SupabaseJwtSettings(issuer=ISSUER, secret=SECRET).algorithms == ('HS256',)
    assert SupabaseJwtSettings(
        issuer=ISSUER, jwks_url='https://a.test/jwks'
    ).algorithms == ('RS256', 'ES256')


def test_looks_like_jwt_separates_master_tokens_and_api_keys():
    assert looks_like_jwt(_hs_token())
    assert not looks_like_jwt('ago_' + 'a' * 40)
    assert not looks_like_jwt('ein-master-token-mit.punkt')
    assert not looks_like_jwt('eyJ.nur-zwei')


def test_malformed_header_fields_are_a_401_not_a_500():
    """``get_unverified_header`` wirft bei einer numerischen ``kid`` oder einem
    unbekannten ``crit`` ``InvalidTokenError`` statt ``DecodeError``
    (Codex-Review auf #1622)."""
    def seg(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=').decode()

    for header in ({'alg': 'HS256', 'kid': 123}, {'alg': 'HS256', 'crit': ['unbekannt']}):
        token = f'{seg(header)}.{seg(_claims())}.c2ln'
        assert _reject(_hs_verifier(), token) is JwtErrorCode.MALFORMED


def test_jwks_signing_keys_are_not_cached_without_expiry(jwks_verifier):
    """Nur der JWKS-Satz wird gecacht (mit ``lifespan``); ein Schlüssel-Cache
    ohne Ablauf hielte rotierte Schlüssel gültig (Codex-Review auf #1622)."""
    client = jwks_verifier._jwks_client
    assert client is not None
    assert client.jwk_set_cache is not None
    assert not hasattr(client.get_signing_key, 'cache_info')


def test_rotated_key_is_rejected_after_the_jwks_cache_expires(rsa_key, monkeypatch):
    verifier = SupabaseJwtVerifier(
        SupabaseJwtSettings(
            issuer=ISSUER, jwks_url='http://auth.internal:9999/jwks', jwks_cache_seconds=30
        )
    )
    old_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    old_jwk.update({'kid': 'key-1', 'alg': 'RS256'})
    keys = {'keys': [old_jwk]}
    assert verifier._jwks_client is not None
    monkeypatch.setattr(verifier._jwks_client, 'fetch_data', lambda: keys)
    token = jwt.encode(_claims(), rsa_key, algorithm='RS256', headers={'kid': 'key-1'})
    assert verifier.verify(token).user_id == USER_ID

    # Rotation: ein neuer Schlüssel ersetzt den alten; der Satz-Cache läuft ab
    # (hier simuliert durch Leeren).
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(new_key.public_key(), as_dict=True)
    new_jwk.update({'kid': 'key-2', 'alg': 'RS256'})
    keys['keys'] = [new_jwk]
    assert verifier._jwks_client.jwk_set_cache is not None
    verifier._jwks_client.jwk_set_cache.lifespan = 0  # sofort abgelaufen

    assert _reject(verifier, token) is JwtErrorCode.INVALID_SIGNATURE


def test_empty_jwks_is_key_unavailable(rsa_key, monkeypatch):
    verifier = SupabaseJwtVerifier(
        SupabaseJwtSettings(issuer=ISSUER, jwks_url='http://auth.internal:9999/jwks')
    )
    assert verifier._jwks_client is not None
    monkeypatch.setattr(verifier._jwks_client, 'fetch_data', lambda: {'keys': []})
    token = jwt.encode(_claims(), rsa_key, algorithm='RS256', headers={'kid': 'key-1'})

    assert _reject(verifier, token) is JwtErrorCode.KEY_UNAVAILABLE
