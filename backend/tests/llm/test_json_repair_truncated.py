"""Verhalten von ``_try_repair_truncated_json`` an abgeschnittenem LLM-JSON.

Der Repair-Pfad greift, wenn ein Provider die Antwort am Output-Cap kappt.
Die Spezifikation ist: entweder ``None`` (nicht reparierbar) oder ein String,
der als JSON parst **und** jedes vollstaendig uebertragene Feld erhaelt.
Ein Ergebnis, das parst, aber den Inhalt verloren hat, ist der schlimmere
Fall — der Caller haelt es fuer einen Erfolg.
"""

import json

from app.llm.json_mode import _try_repair_truncated_json


class TestRepairPreservesCompleteFields:
    """Vollstaendig uebertragene Felder ueberleben den Repair."""

    def test_truncation_after_complete_pair_keeps_that_pair(self):
        # Abbruch direkt hinter einem vollstaendigen Paar plus Komma.
        payload = '{"display_name": "Maya", "age": 34,'

        repaired = _try_repair_truncated_json(payload)

        assert repaired is not None, "abgeschnittenes Objekt sollte reparierbar sein"
        parsed = json.loads(repaired)
        assert parsed["display_name"] == "Maya"
        assert parsed["age"] == 34


class TestRepairNeverReturnsBrokenJson:
    """Was zurueckkommt, parst — sonst kommt ``None`` zurueck.

    Der Caller unterscheidet nur ``None`` von "String". Ein zurueckgegebener,
    aber unparsbarer String kostet ihn einen weiteren Parse-Versuch und
    verschleiert im Log die eigentliche Ursache.
    """

    def test_dangling_colon_is_not_repairable(self):
        # Abbruch direkt hinter einem Key-Doppelpunkt: der Wert fehlt komplett,
        # es gibt nichts, was man ehrlich ergaenzen koennte.
        payload = '{"a": 1, "b":'

        assert _try_repair_truncated_json(payload) is None

    def test_open_string_content_is_not_trimmed(self):
        """Whitespace am Ende eines offenen Strings gehoert zum Wert.

        Der Repair schliesst den String — er darf dessen Inhalt dabei nicht
        veraendern. Ein ``rstrip()`` vor dem Anfuegen des Anfuehrungszeichens
        wuerde Leerzeichen und Zeilenumbrueche verschlucken, die Teil des
        uebertragenen Textes sind.
        """
        # Echtes Leerzeichen am Ende des offenen Strings — im uebertragenen
        # Text vorhanden, weil der Cap zwischen zwei Woerter fiel.
        payload = '{"persona": "Maya arbeitet als '

        repaired = _try_repair_truncated_json(payload)

        assert repaired is not None
        assert json.loads(repaired)["persona"] == "Maya arbeitet als "

    def test_truncation_inside_escape_sequence_recovers_prefix(self):
        # Der Cap faellt zwischen Backslash und escaptem Zeichen. Der Backslash
        # gehoert zu einer Sequenz, die es nicht mehr gibt — er muss weg,
        # sonst escaped er das schliessende Anfuehrungszeichen.
        payload = '{"display_name": "Ma\\'

        repaired = _try_repair_truncated_json(payload)

        assert repaired is not None
        assert json.loads(repaired)["display_name"] == "Ma"
