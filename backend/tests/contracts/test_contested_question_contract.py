"""Vertrags-Tests für die Streitfrage eines Laufs (Issue #1778, Schritt 1.4).

Zwei Validator-Fälle aus dem Planschritt: eine Aussage mit
``origin="assistant"`` ist gültig, ``origin="none"`` zusammen mit einer
Aussage ist ungültig.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts import ContestedQuestion

_STATEMENT = "Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen."


class TestContestedQuestionContract:
    def test_aussage_mit_origin_assistant_ist_gueltig(self):
        cq = ContestedQuestion(statement=_STATEMENT, origin="assistant")
        assert cq.origin == "assistant"
        assert cq.statement == _STATEMENT
        assert cq.absence_reason is None

    def test_origin_none_mit_aussage_ist_ungueltig(self):
        with pytest.raises(ValidationError, match="origin=none"):
            ContestedQuestion(statement=_STATEMENT, origin="none")
