from app.services.api_keys_store import ApiKeysStore

def test_api_keys_store_hashing_and_validation():
    store = ApiKeysStore()

    # 1. Create a key
    resp = store.create("Test Key", ["read"])
    token = resp.token
    key_id = resp.key.id

    assert token.startswith("ago_")
    assert resp.key.prefix == f"ago_{token[4:12]}"
    assert resp.key.hashed_token is not None
    assert resp.key.hashed_token != token

    # 2. Validate token
    validated = store.validate_token(token)
    assert validated is not None
    assert validated.id == key_id
    assert validated.last_used_at is not None

    # 3. Validation should update last_used_at
    last_used = validated.last_used_at
    validated2 = store.validate_token(token)
    assert validated2.last_used_at > last_used

    # 4. Revoke key
    store.revoke(key_id)
    revoked = store.get(key_id)
    assert revoked.status == "revoked"

    # 5. Validating a revoked token returns the model with status=revoked
    # (The auth layer should handle rejecting it)
    validated_revoked = store.validate_token(token)
    assert validated_revoked is not None
    assert validated_revoked.status == "revoked"

def test_api_keys_store_invalid_tokens():
    store = ApiKeysStore()
    assert store.validate_token("invalid_token") is None
    assert store.validate_token("ago_invalid") is None

    resp = store.create("Key", ["read"])
    assert store.validate_token(resp.token + "extra") is None
