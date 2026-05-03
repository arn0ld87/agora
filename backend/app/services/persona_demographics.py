"""DACH-Demographie-Quoten für Persona-Namensgenerierung.

Quelle: Destatis Mikrozensus 2024 (Bevölkerung mit Migrationshintergrund),
BFS Schweiz, Statistik Austria — aggregiert. Werte sind explizite Konstanten,
nicht aus dem Internet gezogen, damit Tests deterministisch bleiben.

Schließt Issue #214: Namen-Generierung nach tatsächlicher demographischer
Verteilung statt nur deutschsprachig.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field


class NameOriginQuota(BaseModel):
    """Bevölkerungsanteil und Beispiel-Namen für einen Herkunfts-Bucket."""

    model_config = ConfigDict(extra="forbid")

    bucket: str
    share: float = Field(ge=0.0, le=1.0)
    first_names: list[str]
    last_names: list[str]


DACH_NAME_ORIGIN_QUOTAS: list[NameOriginQuota] = [
    NameOriginQuota(
        bucket="german_native",
        share=0.74,
        first_names=[
            "Lena", "Marie", "Sophie", "Hannah", "Emma", "Laura", "Julia", "Katharina",
            "Anna", "Sarah", "Lisa", "Nora", "Clara", "Mia", "Leonie",
            "Jonas", "Leon", "Felix", "Maximilian", "Tim", "Lukas", "Paul", "Julian",
            "Niklas", "Jan", "Philipp", "David", "Moritz", "Finn", "Tobias",
            "Alex", "Kim", "Robin", "Sam",
        ],
        last_names=[
            "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
            "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
            "Klein", "Wolf", "Neumann", "Schröder", "Zimmermann", "Braun", "Krüger",
            "Hofmann", "Hartmann", "Lange", "Werner", "Krause", "Lehmann", "Schmitz",
            "Maier", "König",
        ],
    ),
    NameOriginQuota(
        bucket="turkish",
        share=0.04,
        first_names=["Yusuf", "Mehmet", "Ali", "Fatma", "Ayşe", "Zeynep", "Murat", "Elif"],
        last_names=["Yılmaz", "Demir", "Öztürk", "Kaya", "Çelik", "Şahin", "Doğan", "Arslan"],
    ),
    NameOriginQuota(
        bucket="arabic_levant",
        share=0.03,
        first_names=["Ahmed", "Omar", "Khalid", "Layla", "Fatima", "Nour", "Ibrahim", "Sara"],
        last_names=["Haddad", "Khoury", "Najjar", "Hassan", "Al-Amin", "Mansour", "Khalil", "Nasser"],
    ),
    NameOriginQuota(
        bucket="polish_eastern",
        share=0.04,
        first_names=["Piotr", "Krzysztof", "Marcin", "Agnieszka", "Katarzyna", "Monika", "Andrzej", "Tomasz"],
        last_names=["Kowalski", "Nowak", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński", "Lewandowski", "Zielński"],
    ),
    NameOriginQuota(
        bucket="ex_yu_balkan",
        share=0.03,
        first_names=["Marko", "Stefan", "Ivan", "Ana", "Maja", "Jovana", "Nikola", "Milica"],
        last_names=["Petrović", "Hodžić", "Marković", "Nikolić", "Jovanović", "Đorđević", "Ilić", "Stanković"],
    ),
    NameOriginQuota(
        bucket="russian_ukrainian",
        share=0.03,
        first_names=["Dmitri", "Aleksei", "Sergei", "Natalia", "Olena", "Iryna", "Andrii", "Oksana"],
        last_names=["Ivanov", "Petrenko", "Sokolova", "Kovalenko", "Shevchenko", "Bondarenko", "Melnyk", "Kravchenko"],
    ),
    NameOriginQuota(
        bucket="italian",
        share=0.02,
        first_names=["Marco", "Luca", "Giulia", "Sofia", "Matteo", "Lorenzo", "Chiara", "Valentina"],
        last_names=["Rossi", "Esposito", "Ferrari", "Russo", "Bianchi", "Marino", "Greco", "Bruno"],
    ),
    NameOriginQuota(
        bucket="other_european",
        share=0.04,
        first_names=["Jean", "Pierre", "Carlos", "Maria", "João", "Nikos", "Pavlos", "Radu"],
        last_names=["Lefèvre", "García", "Costa", "Silva", "Papadopoulos", "Popescu", "Dubois", "Martin"],
    ),
    NameOriginQuota(
        bucket="asian",
        share=0.02,
        first_names=["Minh", "Linh", "Ji-won", "Min-jun", "Wei", "Fang", "Yuki", "Haruto"],
        last_names=["Nguyen", "Kim", "Wang", "Chen", "Tanaka", "Suzuki", "Pham", "Le"],
    ),
    NameOriginQuota(
        bucket="african_other",
        share=0.01,
        first_names=["Chidi", "Amara", "Kwame", "Aisha", "Fatou", "Mamadou", "Emeka", "Zainab"],
        last_names=["Okafor", "Diallo", "Traore", "Mensah", "Adeyemi", "Nwosu", "Camara", "Bah"],
    ),
]

# Summen-Validierung — schlägt sofort bei Import fehl, wenn jemand Werte ändert.
assert abs(sum(q.share for q in DACH_NAME_ORIGIN_QUOTAS) - 1.0) < 0.01, (
    f"DACH_NAME_ORIGIN_QUOTAS-Summe ist {sum(q.share for q in DACH_NAME_ORIGIN_QUOTAS):.4f}, erwartet 1.0 ± 0.01"
)


# ---------------------------------------------------------------------------
# Regel-basierter Bucket-Klassifizierer
# ---------------------------------------------------------------------------

# Unicode-Normalform NFC für konsistente Zeichen-Vergleiche.
def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# Buchstaben-Muster pro Bucket (Teilmenge genügt — fail-soft zu german_native).
# Nur eindeutig türkische Zeichen — Ö/ö und Ü/ü sind auch deutsch und werden ausgelassen.
_TURKISH_CHARS = re.compile(r"[İıŞşĞğ]")
_SLAVIC_CHARS = re.compile(r"[ćčšžđ]", re.IGNORECASE)          # ex_yu
_POLISH_CHARS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
_CYRILLIC_CHARS = re.compile(r"[Ѐ-ӿ]")

# Suffix/Last-Name-Listen für schnellere Lookup
_TURKISH_SUFFIXES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "turkish" for n in q.last_names}
_ARABIC_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "arabic_levant" for n in q.last_names + q.first_names}
_EX_YU_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "ex_yu_balkan" for n in q.last_names + q.first_names}
_POLISH_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "polish_eastern" for n in q.last_names + q.first_names}
_RU_UA_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "russian_ukrainian" for n in q.last_names + q.first_names}
_ITALIAN_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "italian" for n in q.last_names + q.first_names}
_ASIAN_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "asian" for n in q.last_names + q.first_names}
_AFRICAN_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "african_other" for n in q.last_names + q.first_names}
_OTHER_EUR_NAMES = {_nfc(n.lower()) for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket == "other_european" for n in q.last_names + q.first_names}


def classify_name_origin(full_name: str) -> str:
    """Ordnet einen vollen Namen einem demographischen Bucket zu.

    Regelbasiert, kein LLM. Unbekannte Namen → "german_native" (konservativ).
    Reihenfolge: spezifischere Muster (character-sets) vor generischen Lookups.
    """
    if not full_name or not full_name.strip():
        return "german_native"

    name_nfc = _nfc(full_name.strip())
    tokens = [t.lower() for t in name_nfc.split()]
    tokens_nfc = [_nfc(t) for t in tokens]

    # 1. Türkisch: spezifische Unicode-Zeichen (ı, ş, ğ, ç …)
    if _TURKISH_CHARS.search(name_nfc):
        return "turkish"
    if any(t in _TURKISH_SUFFIXES for t in tokens_nfc):
        return "turkish"

    # 2. Ex-YU: ć, č, š, ž, đ
    if _SLAVIC_CHARS.search(name_nfc):
        return "ex_yu_balkan"
    if any(t in _EX_YU_NAMES for t in tokens_nfc):
        return "ex_yu_balkan"

    # 3. Polnisch/Ostslawisch: ą, ę, ł, ń, ś, ź, ż
    if _POLISH_CHARS.search(name_nfc):
        return "polish_eastern"
    if any(t in _POLISH_NAMES for t in tokens_nfc):
        return "polish_eastern"

    # 4. Russisch/Ukrainisch: Kyrillisch
    if _CYRILLIC_CHARS.search(name_nfc):
        return "russian_ukrainian"
    if any(t in _RU_UA_NAMES for t in tokens_nfc):
        return "russian_ukrainian"

    # 5. Arabisch/Levante: Name-Lookup
    if any(t in _ARABIC_NAMES for t in tokens_nfc):
        return "arabic_levant"

    # 6. Asiatisch: Name-Lookup
    if any(t in _ASIAN_NAMES for t in tokens_nfc):
        return "asian"

    # 7. Afrikanisch: Name-Lookup
    if any(t in _AFRICAN_NAMES for t in tokens_nfc):
        return "african_other"

    # 8. Italienisch: Name-Lookup
    if any(t in _ITALIAN_NAMES for t in tokens_nfc):
        return "italian"

    # 9. Sonstige Europäisch: Name-Lookup
    if any(t in _OTHER_EUR_NAMES for t in tokens_nfc):
        return "other_european"

    # Fallback: deutsch-einheimisch
    return "german_native"


def build_name_quota_prompt_block(n_personas: int = 20) -> str:
    """Erzeugt den Pflicht-Block für Persona-Prompts (DACH-Mikrozensus-Namensverteilung).

    Args:
        n_personas: Anzahl der Personas im Batch (für absolute Zählung im Hinweis).

    Returns:
        Prompt-Abschnitt als String (einbettbar in f-Strings).
    """
    lines = [
        "NAMENSVERTEILUNG (PFLICHT — DACH-Mikrozensus 2024):",
        f"Erzeuge Personas mit Namen entsprechend dieser Verteilung. Bei N={n_personas} Personas zähle aus:",
    ]
    for q in DACH_NAME_ORIGIN_QUOTAS:
        count = max(0, round(q.share * n_personas))
        examples = q.first_names[:2] + q.last_names[:2]
        example_str = ", ".join(examples)
        lines.append(f"- {q.share * 100:.0f} % {q.bucket} (~{count}): z. B. {example_str}")

    lines += [
        "",
        "Verboten: Nur deutsche Namen verwenden.",
        "Verboten: Diversity-Floskeln statt echter demographischer Verteilung.",
    ]
    return "\n".join(lines)


def build_name_quota_prompt_block_en(n_personas: int = 20) -> str:
    """Same as build_name_quota_prompt_block but for the English prompt variant."""
    lines = [
        "NAME DISTRIBUTION (MANDATORY — DACH Mikrozensus 2024):",
        f"Generate personas with names matching this distribution. For N={n_personas} personas, count out:",
    ]
    for q in DACH_NAME_ORIGIN_QUOTAS:
        count = max(0, round(q.share * n_personas))
        examples = q.first_names[:2] + q.last_names[:2]
        example_str = ", ".join(examples)
        lines.append(f"- {q.share * 100:.0f} % {q.bucket} (~{count}): e.g. {example_str}")

    lines += [
        "",
        "Forbidden: Use only German names.",
        "Forbidden: Diversity buzzwords instead of actual demographic distribution.",
    ]
    return "\n".join(lines)
