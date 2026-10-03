"""Längengrenzen für Beiträge je Plattform und Voice-Register.

Issue #1759, Befund A7: Im Referenzlauf maßen 60 Twitter-Kommentare im Schnitt
461 Zeichen, mehr als Twitter selbst zulässt. Die Grenze steht als Vorgabe im
Agenten-Prompt (``agent_tools.augment_profile_with_stance`` hängt sie an den
Profiltext, den OASIS in den System-Prompt übernimmt); die OASIS-Quelle bleibt
unangetastet. Alle Grenzwerte stehen hier und nirgends sonst.

Reihenfolge: Twitter deutlich kürzer als Reddit; die Betroffenen-Register
(``betroffen-de``, ``emotional-de``, ``umgangssprachlich-de``) kürzer als
``formal-de``.
"""

from __future__ import annotations

from typing import Dict

PLATFORM_TWITTER = "twitter"
PLATFORM_REDDIT = "reddit"

#: Höchstzahl Zeichen je Beitrag/Kommentar: Plattform -> Register -> Grenze.
MAX_POST_CHARS: Dict[str, Dict[str, int]] = {
    PLATFORM_TWITTER: {
        "formal-de": 280,
        "technical-de": 250,
        "neutral-de": 240,
        "skeptisch-de": 240,
        "betroffen-de": 200,
        "emotional-de": 160,
        "umgangssprachlich-de": 140,
    },
    PLATFORM_REDDIT: {
        "formal-de": 900,
        "technical-de": 800,
        "neutral-de": 700,
        "skeptisch-de": 700,
        "betroffen-de": 550,
        "emotional-de": 450,
        "umgangssprachlich-de": 350,
    },
}

#: Grenze für ein unbekanntes Register (Altprofil ohne ``voice_register``).
DEFAULT_MAX_POST_CHARS: Dict[str, int] = {PLATFORM_TWITTER: 240, PLATFORM_REDDIT: 700}

#: Durchschnittliche Zeichen je Wort (inkl. Leerzeichen) für die Wortangabe im Prompt.
CHARS_PER_WORD = 6


def max_post_chars(platform: str, voice_register: str | None) -> int:
    """Höchstlänge eines Beitrags für Plattform und Register."""
    per_register = MAX_POST_CHARS.get(platform)
    if per_register is None:
        platform = PLATFORM_REDDIT
        per_register = MAX_POST_CHARS[platform]
    return per_register.get(voice_register or "", DEFAULT_MAX_POST_CHARS[platform])


def build_length_section(platform: str, voice_register: str | None) -> str:
    """Prompt-Abschnitt „Beitragslänge“ für den Agenten."""
    limit = max_post_chars(platform, voice_register)
    words = limit // CHARS_PER_WORD
    return (
        "## Beitragslänge\n"
        f"Schreibe jeden Beitrag und jeden Kommentar in höchstens {limit} Zeichen "
        f"(etwa {words} Wörter). Fasse dich kurz; ein Gedanke pro Beitrag.\n"
    )
