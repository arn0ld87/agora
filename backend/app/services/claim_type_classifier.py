"""Deterministische Claim-Typisierung (Issue #1400).

Der Vorfilter in ``report_agent/sections.py`` verwirft Überschriften und
Gliederungsansagen, bevor ein Claim entsteht (#1316). Was ihn passiert, lief
bisher ausnahmslos als Tatsachenbehauptung durch den Evidence-Index — auch
„Der Träger sollte zunächst eine Station pilotieren" oder „Daraus ergibt sich
ein Zielkonflikt zwischen Tempo und Akzeptanz". Solche Sätze haben naturgemäß
keine direkte Evidence und landeten dadurch bei ``speculative``.

Die Klassifikation ist bewusst regelbasiert und konservativ: im Zweifel
``empirical``. Ein fälschlich als Empfehlung typisierter Tatsachensatz würde
dem Evidence-Gating entgehen — ein fälschlich empirischer Empfehlungssatz
wird nur zu streng bewertet, wie bisher.

Reihenfolge:

1. Zahlen → ``empirical``. Eine Zahl ist prüfbar, auch in einer Empfehlung
   („sollte 70 % erreichen" enthält eine Mengenbehauptung).
2. Struktur-/Meta-Sätze → ``structural``.
3. Handlungsempfehlung (Konjunktiv-Modal, Gerundiv, „empfehlen") →
   ``recommendation``. Indikativ-Modalverben (``soll``, ``muss``) bleiben
   empirisch: „Der Träger muss 22 Dozenten beschäftigen" berichtet eine
   Vorgabe aus der Quelle und ist gegen sie prüfbar.
4. Kausal-/Schlussmarker → ``analytical``. Hedge-Wörter („vermutlich",
   „wahrscheinlich") gehören nicht dazu: sie markieren eine unsichere
   Tatsachenbehauptung, keine Analyse (Hedge-Snapshot, ADR-0002 Anker 2).
5. Sonst ``empirical``.

Folgen je Typ (``confidence_calculator.apply_claim_type_floor`` und
``ReportAgent._finalize_section_claims``):

- Mit stützender Evidence gilt für alle drei nicht-empirischen Typen der
  Boden ``low`` statt ``speculative``.
- Ohne stützende Evidence bleibt jeder Typ außerhalb von ``claims[]``
  (ADR-0002: ein Claim braucht einen Beleg; der Zod-Spiegel prüft das
  ebenfalls). ``recommendation``/``structural`` sind aber keine
  Tatsachenbehauptungen: sie werden als Hypothese mit ihrem Typ geführt und
  erzeugen keine Datenlücke. ``analytical`` trägt faktische Prämissen („…,
  weil sie keinen Anteil an der Entlastung haben") und läuft wie ein
  empirischer Claim.
- Kein Typ-Boden reicht über ``low`` hinaus. ``medium`` und höher bleiben
  allein über Evidence und die ADR-0002-Validatoren erreichbar.
"""

from __future__ import annotations

import re

from app.contracts.report_contract import ClaimType

_NUMBER_RE = re.compile(r"\d")

_STRUCTURAL_RE = re.compile(
    r"^(?:zusammenfassend|abschließend|abschliessend|insgesamt\s+lassen\s+sich"
    r"|im\s+(?:überblick|ueberblick|ergebnis\s+lassen\s+sich)"
    r"|(?:die\s+)?folgende[n]?\s+(?:punkte|aspekte|abschnitte|befunde)"
    r"|(?:drei|vier|fünf|zwei|mehrere)\s+(?:punkte|aspekte|konfliktlinien|befunde|faktoren)\s+"
    r"(?:sind|stehen|prägen|praegen)"
    r"|dieser\s+(?:bericht|report|abschnitt)|der\s+(?:bericht|report)\s+"
    r"(?:gliedert|behandelt|beschreibt|fasst))",
    re.IGNORECASE,
)

_RECOMMENDATION_RE = re.compile(
    r"\b(?:sollte|sollten|empfiehlt|empfehlen|empfohlen|empfehlenswert|ratsam"
    r"|anzuraten|angeraten|wir\s+raten|wäre\s+(?:sinnvoll|ratsam|zu)"
    r"|waere\s+(?:sinnvoll|ratsam|zu)|gilt\s+es|es\s+bietet\s+sich\s+an"
    r"|(?:ist|sind)\s+(?:\w+\s+){0,5}zu\s+(?:prüfen|pruefen|klären|klaeren|vermeiden"
    r"|verankern|sichern|priorisieren|beginnen|starten|regeln|vereinbaren|definieren"
    r"|schaffen|stärken|staerken|begrenzen|überprüfen|ueberpruefen|entscheiden))\b",
    re.IGNORECASE,
)

_ANALYTICAL_RE = re.compile(
    r"\b(?:weil|deshalb|daher|folglich|somit|dadurch|infolgedessen|demnach"
    r"|führt\s+zu|fuehrt\s+zu|führen\s+zu|fuehren\s+zu|deutet\s+darauf\s+hin"
    r"|spricht\s+dafür|spricht\s+dafuer|daraus\s+ergibt"
    r"|daraus\s+folgt|zielkonflikt|spannungsfeld"
    r"|hängt\s+davon\s+ab|haengt\s+davon\s+ab)\b",
    re.IGNORECASE,
)


def classify_claim_type(text: str) -> ClaimType:
    """Typisiert einen bereits vorgefilterten Claim-Satz."""
    stripped = (text or "").strip()
    if not stripped or _NUMBER_RE.search(stripped):
        return ClaimType.empirical
    if _STRUCTURAL_RE.search(stripped):
        return ClaimType.structural
    if _RECOMMENDATION_RE.search(stripped):
        return ClaimType.recommendation
    if _ANALYTICAL_RE.search(stripped):
        return ClaimType.analytical
    return ClaimType.empirical


__all__ = ["classify_claim_type"]
