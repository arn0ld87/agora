"""Guard gegen maschinenübersetzte Log- und Fortschrittsmeldungen.

``report_agent`` und Teile der Prepare-API stammen aus einem chinesischsprachigen
Upstream-Fork. Beim Übersetzen sind Meldungen wie ``"outlinesaved: %s"``,
``"reportgeneratefailed"`` oder ``"Section … reachedmaximumiterationscount，
Forcegenerate"`` entstanden: Wortgrenzen sind verlorengegangen und
Fullwidth-Interpunktion (``，``, ``（``, ``）``) ist stehengeblieben.

Das ist kein Kosmetikproblem. Die Fortschrittsmeldungen aus
``ReportManager.update_progress`` und ``progress_callback`` gehen unverändert an
die Oberfläche, und die Log-Zeilen sind der einzige Anhaltspunkt, wenn ein
Report-Lauf nachts abbricht.

Der Guard prüft zwei Signaturen dieser Fehlerklasse — Fullwidth-Interpunktion und
zusammengeklebte Wörter — an genau den Stellen, an denen sie aufgetreten ist:
``logger.*``-Aufrufe, ``update_progress`` und ``progress_callback``. Er ist
bewusst eine Heuristik mit einer geschlossenen Wortliste, kein
Rechtschreibprüfer: er soll den Rückfall beim nächsten Upstream-Merge fangen,
nicht Prosa bewerten.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

#: Interpunktion aus dem CJK-Zeichensatz. In einer englischen Meldung ist sie
#: immer ein Übersetzungsrest.
FULLWIDTH_PUNCTUATION = "，。、（）：；！？「」『』〜・"

LOGGER_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "critical", "exception"}
)

#: Funktionen, deren String-Argumente ebenfalls beim Nutzer landen.
USER_FACING_CALLS = frozenset({"update_progress", "progress_callback"})

#: Wörter, die in der Fehlerklasse tatsächlich zusammengeklebt aufgetreten sind,
#: plus die naheliegenden Nachbarn aus demselben Vokabular. Bewusst kurz
#: gehalten: jedes zusätzliche Wort erhöht die Chance auf einen Fehlalarm in
#: einer Meldung, die nur zufällig zwei davon aneinanderreiht.
VOCABULARY = frozenset(
    {
        "agent",
        "chat",
        "complete",
        "completed",
        "content",
        "count",
        "delete",
        "deleted",
        "entity",
        "failed",
        "folder",
        "generate",
        "generated",
        "generating",
        "initialize",
        "iterations",
        "maximum",
        "outline",
        "report",
        "saved",
        "section",
        "sections",
        "times",
    }
)

#: Alle Klebefälle als Suchmuster — ein Wort direkt am nächsten, ohne
#: Leerzeichen, Unterstrich oder Satzzeichen dazwischen.
GLUED_PAIRS = tuple(
    sorted(
        (first, second)
        for first in VOCABULARY
        for second in VOCABULARY
        if first != second
    )
)


def _python_sources() -> list[Path]:
    return sorted(p for p in APP_DIR.rglob("*.py") if ".venv" not in p.parts)


def _is_relevant_call(node: ast.Call) -> bool:
    """``logger.info(...)``, ``…update_progress(...)`` oder ``progress_callback(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr in USER_FACING_CALLS:
            return True
        if func.attr not in LOGGER_METHODS:
            return False
        # Nur echte Logger, nicht beliebige ``x.info(...)``-Aufrufe. Geprüft
        # wird das Attribut direkt vor der Methode: bei ``self.logger.error(…)``
        # heißt die Wurzel ``self`` und trägt kein ``log`` im Namen — sie allein
        # anzusehen ließe jeden instanzgebundenen Logger durchrutschen.
        target = func.value
        while isinstance(target, ast.Attribute):
            if "log" in target.attr.lower():
                return True
            target = target.value
        return isinstance(target, ast.Name) and "log" in target.id.lower()
    return isinstance(func, ast.Name) and func.id in USER_FACING_CALLS


def _message_fragments(node: ast.Call) -> list[tuple[str, str | None, str | None]]:
    """Konstante Textstücke eines Aufrufs als ``(text, davor, danach)``.

    ``davor``/``danach`` sind ``None``, wenn das Fragment nicht an einen
    ``{}``-Platzhalter grenzt. Genau an diesen Grenzen entstehen Klebefälle, die
    im reinen Literaltext unsichtbar bleiben (``f"total{n}sections"``).
    """
    fragments: list[tuple[str, str | None, str | None]] = []
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            fragments.append((arg.value, None, None))
        elif isinstance(arg, ast.JoinedStr):
            parts = arg.values
            for index, part in enumerate(parts):
                if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                    continue
                before = "placeholder" if index > 0 else None
                after = "placeholder" if index + 1 < len(parts) else None
                fragments.append((part.value, before, after))
    return fragments


def _glued_pair(text: str, lowered: str) -> str | None:
    """Erstes zusammengeklebtes Wortpaar — ``CamelCase`` ausgenommen.

    ``ReportAgent``, ``ReportManager`` und ``ReportSection`` sind Klassennamen und
    stehen zu Recht in Meldungen. Der Übersetzungsfehler sieht anders aus: dort
    beginnt das zweite Wort klein (``Sectionsaved``, ``reportgeneratefailed``).
    Der Großbuchstabe an der Wortgrenze ist damit das verlässliche
    Unterscheidungsmerkmal.
    """
    for first, second in GLUED_PAIRS:
        glued = first + second
        start = lowered.find(glued)
        while start != -1:
            if not text[start + len(first)].isupper():
                return glued
            start = lowered.find(glued, start + 1)
    return None


def _trailing_word(text: str) -> str:
    tail = ""
    for char in reversed(text):
        if not char.isalpha():
            break
        tail = char + tail
    return tail.lower()


def _leading_word(text: str) -> str:
    head = ""
    for char in text:
        if not char.isalpha():
            break
        head += char
    return head.lower()


def _findings() -> list[str]:
    problems: list[str] = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_relevant_call(node)):
                continue
            where = f"{path.relative_to(APP_DIR.parent)}:{node.lineno}"
            for text, before, after in _message_fragments(node):
                lowered = text.lower()
                bad_chars = sorted({c for c in text if c in FULLWIDTH_PUNCTUATION})
                if bad_chars:
                    problems.append(
                        f"{where}: Fullwidth-Interpunktion {bad_chars} in {text!r}"
                    )
                glued = _glued_pair(text, lowered)
                if glued:
                    problems.append(
                        f"{where}: zusammengeklebte Wörter {glued!r} in {text!r}"
                    )
                # Am Platzhalter zählt nur das direkt angrenzende Wort: hinter
                # einem ``{}`` das erste, davor das letzte.
                if before and _leading_word(text) in VOCABULARY:
                    problems.append(
                        f"{where}: {_leading_word(text)!r} klebt am vorangehenden "
                        f"Platzhalter in {text!r}"
                    )
                if after and _trailing_word(text) in VOCABULARY:
                    problems.append(
                        f"{where}: {_trailing_word(text)!r} klebt am folgenden "
                        f"Platzhalter in {text!r}"
                    )
    return problems


def test_no_machine_translated_log_messages() -> None:
    """Keine Meldung in ``backend/app`` trägt die Spuren der Fehlübersetzung.

    Schlägt der Test an, ist die Meldung selbst zu reparieren — nicht die
    Wortliste zu kürzen. Ein echter Fehlalarm (zwei Vokabelwörter, die
    zufälligerweise aneinandergrenzen) wird an der Wortliste behoben und in ihrem
    Kommentar begründet.
    """
    problems = _findings()
    assert not problems, "Fehlerhafte Log-/Fortschrittsmeldungen:\n" + "\n".join(problems)


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        pytest.param(
            'logger.info(f"outlinesaved: {report_id}")',
            "zusammengeklebte Wörter",
            id="geklebte-woerter-im-literal",
        ),
        pytest.param(
            'logger.warning(f"Section {t} reachedmaximumiterationscount，Forcegenerate")',
            "Fullwidth-Interpunktion",
            id="fullwidth-interpunktion",
        ),
        pytest.param(
            'update_progress(rid, "planning", 15, f"total{n}sections")',
            "klebt am vorangehenden Platzhalter",
            id="klebt-an-platzhalter",
        ),
        pytest.param(
            'self.logger.error(f"reportgeneratefailed: {e}")',
            "zusammengeklebte Wörter",
            id="instanzgebundener-logger",
        ),
    ],
)
def test_guard_detects_the_original_defects(
    snippet: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gegenprobe: der Guard erkennt die Formen, wegen derer er existiert.

    Ohne diesen Nachweis wäre der Guard oben auch dann grün, wenn die Heuristik
    gar nichts mehr findet — etwa nach einem Refactor, der ``_is_relevant_call``
    versehentlich immer ``False`` liefern lässt.
    """
    (tmp_path / "sample.py").write_text(snippet, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "APP_DIR", tmp_path)

    problems = _findings()

    assert any(expected in problem for problem in problems), (
        f"Guard hat {snippet!r} nicht beanstandet; gefunden wurde:\n" + "\n".join(problems)
    )


def test_camel_case_class_names_are_not_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``ReportAgent`` & Co. sind Klassennamen, keine verschmolzenen Wörter.

    Ohne diese Ausnahme wäre der Guard nur dadurch grün zu bekommen, dass man
    Klassennamen aus Meldungen entfernt — und würde damit genau die
    Diagnose-Information kosten, um die es hier geht.
    """
    (tmp_path / "sample.py").write_text(
        'logger.info("ReportAgent initialization complete: graph_id=%s", graph_id)\n'
        'logger.debug("ReportManager wrote the ReportSection to disk")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "APP_DIR", tmp_path)

    assert _findings() == []
