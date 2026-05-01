"""
Cypher-Label-Sanitizer-Regression (Slice 12, F5 of repo review).

Locks ``app.storage.neo4j_mappings.sanitize_label`` against the cases the
review explicitly demanded — backticks (Cypher injection vector), oversized
labels, special characters, empty strings — plus a positive control that
ordinary identifiers pass through.

This is a focused companion to the broader ``test_neo4j_mappings.py``: it
documents the security-relevant subset under a name auditors expect to find.
"""

from __future__ import annotations

import pytest

from app.storage.neo4j_mappings import sanitize_label


# ── Positive control ────────────────────────────────────────────────────────


@pytest.mark.parametrize("label", ["Person", "Organization", "_Internal", "Film", "A" * 50])
def test_passes_regular_identifiers(label: str):
    """Plain Cypher-identifier-shaped labels round-trip unchanged."""
    assert sanitize_label(label) == label


# ── Injection / hostile input ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "hostile",
    [
        "Person`}; DROP DATABASE neo4j; //",
        "`); MATCH (n) DETACH DELETE n; (",
        "Person`Foo",
        "``",
        "name`with`backticks",
    ],
)
def test_neutralises_backtick_injection(hostile: str):
    """Backticks (and the Cypher-fragment that follows) get stripped — the
    return value either becomes a harmless identifier or ``None``, never a
    string that reintroduces the backticks into a Cypher template."""
    cleaned = sanitize_label(hostile)
    if cleaned is not None:
        assert "`" not in cleaned
        assert ";" not in cleaned
        assert "(" not in cleaned and ")" not in cleaned


def test_strips_special_characters():
    """Whitespace becomes ``_``; everything outside ``[A-Za-z0-9_]`` is
    dropped before the regex check."""
    assert sanitize_label("Public Figure") == "Public_Figure"
    # German umlauts get stripped (non-ASCII removed before regex match).
    assert sanitize_label("Bürger") == "Brger"


# ── Hard rejects (return ``None``) ──────────────────────────────────────────


@pytest.mark.parametrize(
    "rejected",
    [
        "",                     # empty
        "   ",                  # whitespace-only
        "Entity",               # default label, intentionally rejected
        "1stClass",             # must start with letter or underscore
        "A" * 51,               # exceeds 50-char cap
        ";",                    # no identifier chars survive normalisation
        "()",
        "`",
        "🦄",                   # non-ASCII only — stripped down to empty
    ],
)
def test_rejects_unusable_input_with_none(rejected: str):
    assert sanitize_label(rejected) is None


@pytest.mark.parametrize("non_string", [None, 42, 3.14, ["Person"], {"label": "Person"}, b"Person"])
def test_rejects_non_string_input(non_string):
    """Anything that is not a ``str`` is rejected outright."""
    assert sanitize_label(non_string) is None


# ── Length-cap edge case ────────────────────────────────────────────────────


def test_50_char_label_passes_51_does_not():
    """The Regex caps the identifier at 50 characters total."""
    assert sanitize_label("X" * 50) == "X" * 50
    assert sanitize_label("X" * 51) is None
