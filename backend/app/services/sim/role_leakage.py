"""Role-Leakage-Erkennung für Simulationsaktionen (Issue #1323, Slice 5.1).

Regelbasierte Analyse: Erkennt Selbstreferenzen in Aktionstext, die auf eine
fremde Persona-Rolle hindeuten (z.B. Agent "Kaufm. Geschäftsführer" schreibt
"Aus Sicht des Technischen Dienstes").

Konservatives Design: Untergrenze statt vollständige Erkennung, da False
Positives den Audit unbrauchbar machen. Keine LLM-Calls, kein Netzwerk.
"""
from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from ...contracts.role_leakage_contract import (
    ConflictReason,
    RoleConflict,
    RoleLeakagePlatformSummary,
    RoleLeakageSummary,
)

# ---------------------------------------------------------------------------
# Muster für Selbstreferenzen
# ---------------------------------------------------------------------------

# Phrase X auf bis zu 6 Wörter, bis Satzzeichen oder Komma
_WORD_SEQ = r"([\w\-/äöüÄÖÜß]+(?:[\s\-]+[\w\-/äöüÄÖÜß]+){0,5})"

_PATTERNS: list[re.Pattern[str]] = [
    # "Aus Sicht des/der/unseres/unserer <X>"
    re.compile(
        r"Aus Sicht (?:des|der|unseres|unserer)\s+" + _WORD_SEQ,
        re.IGNORECASE,
    ),
    # "Als <X> ..." — nur am Satzanfang oder nach Satzzeichen/Zeilenumbruch,
    # damit konjunktionales "als" (z.B. "fühlt man sich, als ...") nicht matcht.
    # "Als" muss von einem Großbuchstaben (deutsches Nomen) gefolgt werden.
    re.compile(
        r"(?:^|(?<=[.!?;\n])\s*)Als\s+([A-ZÄÖÜ][\w\-äöüÄÖÜß]*(?:[\s\-]+[\w\-äöüÄÖÜß]+){0,5})"
        r"(?:\s+(?:unserer|unseres|der|des|im|in|bei|für))?",
        re.MULTILINE,
    ),
    # "Wir (als|vom|von der) <X>"
    re.compile(
        r"Wir\s+(?:als|vom|von der)\s+" + _WORD_SEQ,
        re.IGNORECASE,
    ),
]

# Namens-Signaturen am Ende: "— Vorname Nachname", "Ihre/Eure <Name>",
# "Viele Grüße, <Name>" (Leerzeichen tolerant, Punkte in Titeln erlaubt)
_NAME_PART = r"[\w\.\-äöüÄÖÜß]+"
_NAME_2PLUS = _NAME_PART + r"(?:\s+" + _NAME_PART + r")+"

_NAME_SIGNATURE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[—\-]{1,2}\s*(" + _NAME_2PLUS + r")\s*$", re.MULTILINE),
    re.compile(r"(?:Ihre|Eure|Ihr|Euer)\s+(" + _NAME_2PLUS + r")\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(
        r"(?:Viele\s+Grüße|Mit\s+freundlichen\s+Grüßen|Herzliche\s+Grüße|Grüße)[,\s]+("
        + _NAME_2PLUS + r")\s*$",
        re.MULTILINE | re.IGNORECASE,
    ),
]

# Generische Phrasen, die keinen Konflikt auslösen sollen
_GENERIC_PHRASES: frozenset[str] = frozenset({
    "unternehmen",
    "beispiel",
    "nächstes",
    "naechstes",
    "praxis",
    "allgemein",
    "stakeholder",
    "nutzer",
    "anwender",
    "kunden",
    "bürger",
    "buerger",
    "mitarbeiter",
    "beschäftigte",
    "beschaeftigte",
    "team",
    "teams",
    "gruppen",
    "gruppe",
    "klasse",
    "kollegen",
    "perspektive",
    "seite",
    "erster",
    "letzter",
    "nächster",
    "nächste",
    "schritt",
    "sicht",
    "ansicht",
    "weiteres",
    "weiterer",
    "weitere",
    "experte",
    "experten",
    "fachleute",
    "betroffene",
    "entscheider",
    "verantwortliche",
    "verantwortlicher",
    "leiterin",
    "leiter",
    "jemand",
    "jemanden",
    "jemandem",
    "person",
    "personen",
    "mensch",
    "menschen",
    "einzelner",
    "einzelne",
    "einzelnen",
    "beobachter",
    "beobachterin",
    "außenstehender",
    "außenstehende",
})

# Action-Types mit eigenem Text der Persona
_TEXT_ACTION_TYPES: frozenset[str] = frozenset({
    "CREATE_POST",
    "CREATE_COMMENT",
    "QUOTE_POST",
})

# Genus-Normalisierung (einfache Paare)
_GENUS_MAP: dict[str, str] = {
    "chefärztin": "chefarzt",
    "ärztin": "arzt",
    "leiterin": "leiter",
    "direktorin": "direktor",
    "beauftragte": "beauftragter",
    "pflegerin": "pfleger",
    "mitarbeiterin": "mitarbeiter",
    "referentin": "referent",
    "koordinatorin": "koordinator",
    "managerin": "manager",
    "assistentin": "assistent",
    "verwalterin": "verwalter",
}


# ---------------------------------------------------------------------------
# Text-Normalisierung
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Kleinbuchstaben, Umlaute normalisieren, Sonderzeichen entfernen."""
    text = text.lower().strip()
    # Umlaute explizit normalisieren
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    text = text.replace("ß", "ss")
    # Unicode-Normalisierung
    text = unicodedata.normalize("NFKD", text)
    return text


def _stem(token: str) -> str:
    """Minimales Stemming: Genus-Map + trailing s/n/en/er."""
    t = _normalize(token)
    if t in _GENUS_MAP:
        return _GENUS_MAP[t]
    # Einfaches Stripping
    for suffix in ("innen", "inen", "innen", "erin", "ern", "erinnen",
                   "nen", "en", "er", "es", "s", "n"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 4:
            return t[: -len(suffix)]
    return t


def _tokens(text: str) -> set[str]:
    """Extrahiert normalisierte Token-Stems aus Text."""
    words = re.findall(r"[\wäöüÄÖÜß\-]+", text)
    return {_stem(w) for w in words if len(w) >= 3}


def _is_generic(phrase: str) -> bool:
    """True, wenn die Phrase generisch und damit kein Konflikt-Indikator ist."""
    norm = _normalize(phrase.strip())
    # Exakter Match auf einzelnes generisches Wort
    if norm in _GENERIC_PHRASES:
        return True
    # Erste Token generisch
    first = norm.split()[0] if norm.split() else ""
    if first in _GENERIC_PHRASES:
        return True
    return False


#: Rollen, die in Profilen und Texten unter verschiedenen Bezeichnungen
#: auftreten. Ein Umschüler, der „Als Teilnehmer …" schreibt, spricht aus
#: eigener Rolle. Stämme nach :func:`_role_stem`.
_ROLE_SYNONYMS: tuple[frozenset[str], ...] = (
    frozenset({"teilnehm", "umschuel", "retrain", "auszubild", "azubi", "lernend"}),
    frozenset({"dozent", "lehrkraft", "lehr", "trainer", "ausbild"}),
    frozenset({"pfleg", "pflegekraft", "krankenpfleg"}),
)

_ROLE_SUFFIXES = ("innen", "erin", "in", "en", "es", "e", "s", "n")

#: Mindestlänge eines gemeinsamen Bestimmungsworts („betriebsrats").
_COMPOUND_PREFIX_MIN = 9


def _role_stem(word: str) -> str:
    """Stamm eines Rollen-Nomens: Genus und Plural abgeschnitten."""
    t = _normalize(word).strip("-/")
    t = _GENUS_MAP.get(t, t)
    for suffix in _ROLE_SUFFIXES:
        if t.endswith(suffix) and len(t) - len(suffix) >= 4:
            return t[: -len(suffix)]
    return t


def _role_head(ref: str) -> Optional[str]:
    """Kopf-Nomen der Selbstreferenz („Dozent in der Umschulung" → dozent).

    Deutsche Nomen und Adjektive im Nominativ-Vorfeld sind groß geschrieben;
    die Rollenbezeichnung endet am ersten klein geschriebenen Wort. Gezählt
    wird ihr letztes Glied — bei „Technischen Dienstes" das Nomen, nicht das
    Adjektiv.
    """
    head: list[str] = []
    for word in ref.split()[:4]:
        if not word[:1].isupper():
            break
        head.append(word)
    if not head:
        return None
    stem = _role_stem(head[-1])
    return stem if len(stem) >= 4 else None


def _synonyms(stem: str) -> frozenset[str]:
    for group in _ROLE_SYNONYMS:
        if any(stem.startswith(member) or member.startswith(stem) for member in group):
            return group
    return frozenset({stem})


def _role_matches(stem: str, identity_text: str) -> bool:
    """Kommt die Rolle (oder ein Synonym) in der Identität vor?

    Teilstring statt Token-Gleichheit: „dozent" steckt in „Honorardozentin"
    und „Fachdozent", deutsche Komposita tragen die Rolle am Wortende.
    """
    if any(member in identity_text for member in _synonyms(stem)):
        return True
    # Komposita mit gemeinsamem Bestimmungswort: „Betriebsratsmitglied" und
    # „Betriebsratsvorsitzende" bezeichnen dieselbe Rollenfamilie.
    return any(
        len(os.path.commonprefix([stem, token])) >= _COMPOUND_PREFIX_MIN
        for token in identity_text.split()
    )


def _identity_text(persona: Optional[dict], agent_name: str = "") -> str:
    """Normalisierter Identitätstext: Name, Beruf, Typ, Anfang der Selbstbeschreibung."""
    parts: list[str] = [agent_name]
    if persona:
        for key in ("name", "profession", "source_entity_type"):
            parts.append(str(persona.get(key) or ""))
        for key in ("user_char", "description", "bio", "persona"):
            parts.append(str(persona.get(key) or "")[:150])
    return _normalize(" ".join(p for p in parts if p))


def _foreign_identity_text(persona: dict) -> str:
    """Nur die harte Rolle einer anderen Persona — keine Selbstbeschreibung."""
    return _normalize(
        " ".join(str(persona.get(k) or "") for k in ("name", "profession", "source_entity_type"))
    )


# ---------------------------------------------------------------------------
# Persona-Identitäts-Extraktion
# ---------------------------------------------------------------------------


def _persona_identity_tokens(persona: dict) -> set[str]:
    """Extrahiert Token-Set aus name, profession, source_entity_type, bio/persona."""
    parts: list[str] = []
    for field in ("name", "profession", "source_entity_type"):
        v = persona.get(field)
        if v:
            parts.append(str(v))
    # Nur die ersten 200 Zeichen von bio/persona (Kern-Identität)
    for field in ("bio", "persona"):
        v = persona.get(field)
        if v:
            parts.append(str(v)[:200])
    combined = " ".join(parts)
    return _tokens(combined)


# ---------------------------------------------------------------------------
# Profil-Laden
# ---------------------------------------------------------------------------


def _load_reddit_profiles(sim_dir: Path) -> list[dict]:
    """Lädt reddit_profiles.json; gibt leere Liste bei Fehler."""
    path = sim_dir / "reddit_profiles.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def _load_twitter_profiles(sim_dir: Path) -> list[dict]:
    """Lädt twitter_profiles.csv; gibt leere Liste bei Fehler."""
    path = sim_dir / "twitter_profiles.csv"
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except (OSError, csv.Error, ValueError):
        return []


def _enrich_from_reddit(twitter: list[dict], reddit: list[dict]) -> list[dict]:
    """Ergänzt Twitter-Profile um Beruf und Typ aus dem Reddit-Profil.

    ``twitter_profiles.csv`` trägt keinen Beruf. Beide Dateien entstehen aus
    derselben Persona-Liste in derselben Reihenfolge; ergänzt wird nur, wenn
    der Name am gleichen Index übereinstimmt.
    """
    enriched: list[dict] = []
    for idx, row in enumerate(twitter):
        merged = dict(row)
        if idx < len(reddit) and reddit[idx].get("name") == row.get("name"):
            for key in ("profession", "source_entity_type", "persona", "bio"):
                merged.setdefault(key, reddit[idx].get(key))
        enriched.append(merged)
    return enriched


def _resolve_persona(profiles: list[dict], agent_id: int) -> Optional[dict]:
    """Index-first, dann user_id-Fallback (wie interview_direct._resolve_persona)."""
    if 0 <= agent_id < len(profiles):
        return profiles[agent_id]
    for p in profiles:
        raw_id = p.get("user_id")
        try:
            if raw_id is not None and int(raw_id) == agent_id:
                return p
        except (TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Öffentliche Helfer für den action_log_reader-Pfad (Slice 5.2)
# ---------------------------------------------------------------------------


def load_profiles(sim_dir: Path | str) -> tuple[list[dict], list[dict]]:
    """Lädt und kombiniert Plattform-Profile für ein Simulationsverzeichnis.

    Gibt ``(twitter_profiles, reddit_profiles)`` zurück; beide Listen können
    leer sein, wenn die Dateien fehlen oder nicht lesbar sind. Die
    Twitter-Profile werden mit den Reddit-Profilen angereichert (Beruf, Typ),
    wenn die Namen am gleichen Index übereinstimmen.

    Wird einmal pro Simulation geladen und vom Aufrufer gecacht.
    """
    sim_path = Path(sim_dir)
    reddit = _load_reddit_profiles(sim_path)
    twitter = _enrich_from_reddit(_load_twitter_profiles(sim_path), reddit)
    return twitter, reddit


def detect_role_conflict(
    platform: str,
    action_dict: dict,
    profiles: list[dict],
) -> Optional[str]:
    """Prüft einen Action-Dict auf Rollenvertauschung und gibt den Grund zurück.

    Parameters
    ----------
    platform:
        ``"twitter"`` oder ``"reddit"`` — bestimmt, welches Profil-Set
        übergeben wird.
    action_dict:
        Roher Action-Dict (Felder: ``agent_id``, ``agent_name``,
        ``action_type``, ``action_args``, ``round``).
    profiles:
        Fertig angereichertes Plattform-Profil-Set (Twitter oder Reddit),
        wie von :func:`load_profiles` geliefert.

    Returns
    -------
    str | None
        ``RoleConflict.reason`` als Zeichenkette (z. B. ``"foreign_role"``,
        ``"foreign_name_signature"``, ``"unmatched_self_reference"``), oder
        ``None`` wenn kein Konflikt erkannt wurde.
    """
    action_type = action_dict.get("action_type", "")
    if action_type not in _TEXT_ACTION_TYPES:
        return None

    agent_id_raw = action_dict.get("agent_id", 0)
    try:
        agent_id = int(agent_id_raw)
    except (TypeError, ValueError):
        agent_id = 0

    conflict = check_action(
        platform=platform,
        round_num=action_dict.get("round", 0),
        agent_id=agent_id,
        agent_name=action_dict.get("agent_name", ""),
        action_type=action_type,
        action_args=action_dict.get("action_args", {}),
        own_persona=_resolve_persona(profiles, agent_id),
        all_personas=profiles,
    )
    return conflict.reason if conflict is not None else None


# ---------------------------------------------------------------------------
# Konflikt-Erkennung
# ---------------------------------------------------------------------------


def _extract_self_references(text: str) -> list[str]:
    """Extrahiert Selbstreferenz-Phrasen aus Text."""
    refs: list[str] = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            phrase = m.group(1).strip()
            # Kürzen bei Satzzeichen/Komma
            phrase = re.split(r"[,;.!?]", phrase)[0].strip()
            # Tokenanzahl prüfen (max 6 Wörter)
            if 1 <= len(phrase.split()) <= 6:
                refs.append(phrase)
    return refs


def _extract_name_signatures(text: str) -> list[str]:
    """Extrahiert Namens-Signaturen aus dem Text."""
    sigs: list[str] = []
    for pattern in _NAME_SIGNATURE_PATTERNS:
        for m in pattern.finditer(text):
            sig = m.group(1).strip()
            # Muss mindestens Vor- und Nachname sein (2 Wörter)
            if len(sig.split()) >= 2:
                sigs.append(sig)
    return sigs


def _overlap(set_a: set[str], set_b: set[str], min_overlap: int = 1) -> bool:
    """True, wenn mindestens min_overlap gemeinsame Stems vorhanden."""
    # Ignoriere sehr kurze Tokens (< 4 Buchstaben vor Normalisierung)
    meaningful_a = {t for t in set_a if len(t) >= 4}
    meaningful_b = {t for t in set_b if len(t) >= 4}
    return len(meaningful_a & meaningful_b) >= min_overlap


def _action_text(action_type: str, action_args: dict) -> str:
    """Eigener Text der Persona — bei QUOTE_POST nie der zitierte Fremdtext."""
    key = "quote_content" if action_type == "QUOTE_POST" else "content"
    return str(action_args.get(key, "") or "")


def _self_reference_conflict(
    text: str, own_text: str, own_persona: Optional[dict], all_personas: list[dict]
) -> Optional[tuple[ConflictReason, str, Optional[str]]]:
    """Erste Selbstreferenz, die nicht zur eigenen Rolle passt.

    Liefert ``(reason, phrase, matched_role)`` oder ``None``.
    """
    for ref in _extract_self_references(text):
        if _is_generic(ref):
            continue
        head = _role_head(ref)
        if head is None or _normalize(head) in _GENERIC_PHRASES:
            continue
        if _role_matches(head, own_text):
            continue
        for other in all_personas:
            if other is not own_persona and _role_matches(head, _foreign_identity_text(other)):
                return "foreign_role", ref, other.get("profession") or other.get("name")
        return "unmatched_self_reference", ref, None
    return None


def _name_signature_conflict(
    text: str, own_tokens: set[str], all_personas: list[dict]
) -> Optional[tuple[ConflictReason, str, Optional[str]]]:
    """Namens-Signatur einer anderen Persona am Textende."""
    for sig in _extract_name_signatures(text):
        sig_tokens = _tokens(sig)
        if own_tokens and _overlap(sig_tokens, own_tokens):
            continue
        for other in all_personas:
            other_name = other.get("name", "")
            if other_name and _overlap(sig_tokens, _tokens(other_name)):
                return "foreign_name_signature", sig, other_name
    return None


def check_action(
    *,
    platform: str,
    round_num: int,
    agent_id: int,
    agent_name: str,
    action_type: str,
    action_args: dict,
    own_persona: Optional[dict],
    all_personas: list[dict],
) -> Optional[RoleConflict]:
    """Prüft eine einzelne Aktion auf Rollenvertauschung.

    Gibt None zurück, wenn kein Konflikt erkannt wurde.
    """
    if action_type not in _TEXT_ACTION_TYPES:
        return None
    text = _action_text(action_type, action_args)
    if not text:
        return None

    own_tokens: set[str] = _persona_identity_tokens(own_persona) if own_persona else set()
    # Mindestens agent_name als Fallback
    own_tokens.update(_tokens(agent_name))
    own_text = _identity_text(own_persona, agent_name)

    found = _self_reference_conflict(
        text, own_text, own_persona, all_personas
    ) or _name_signature_conflict(text, own_tokens, all_personas)
    if found is None:
        return None
    reason, phrase, matched = found
    return RoleConflict(
        platform=platform,
        round=round_num,
        agent_id=agent_id,
        agent_name=agent_name,
        action_type=action_type,
        excerpt=text[:200],
        self_reference=phrase[:200],
        matched_role=matched,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Plattform-Audit
# ---------------------------------------------------------------------------


def audit_platform(
    sim_dir: Path,
    platform: str,
    profiles: list[dict],
    max_examples: int = 10,
) -> tuple[list[RoleConflict], int]:
    """Analysiert actions.jsonl einer Plattform.

    Gibt (conflicts, text_action_count) zurück.
    """
    log_path = sim_dir / platform / "actions.jsonl"
    if not log_path.exists():
        return [], 0

    conflicts: list[RoleConflict] = []
    text_action_count = 0

    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # round_end und andere Events überspringen
            if "event_type" in data:
                continue
            if "agent_id" not in data:
                continue

            action_type = data.get("action_type", "")
            if action_type not in _TEXT_ACTION_TYPES:
                continue

            text_action_count += 1
            agent_id_raw = data.get("agent_id", 0)
            try:
                agent_id = int(agent_id_raw)
            except (TypeError, ValueError):
                agent_id = 0

            own_persona = _resolve_persona(profiles, agent_id)
            conflict = check_action(
                platform=platform,
                round_num=data.get("round", 0),
                agent_id=agent_id,
                agent_name=data.get("agent_name", ""),
                action_type=action_type,
                action_args=data.get("action_args", {}),
                own_persona=own_persona,
                all_personas=profiles,
            )
            if conflict is not None:
                conflicts.append(conflict)

    return conflicts, text_action_count


# ---------------------------------------------------------------------------
# Gesamt-Audit
# ---------------------------------------------------------------------------


def audit_sim_dir(
    sim_dir_path: str | Path,
    max_examples: int = 5,
) -> RoleLeakageSummary:
    """Führt den vollständigen Role-Leakage-Audit für ein Simulationsverzeichnis durch.

    Liest Twitter- und Reddit-Logs, lädt Profile und erstellt eine Summary.
    """
    sim_dir = Path(sim_dir_path)

    platform_summaries: list[RoleLeakagePlatformSummary] = []
    all_conflicts: list[RoleConflict] = []
    total_text_actions = 0
    total_conflicts = 0
    by_reason_total: dict[str, int] = {}

    reddit_profiles = _load_reddit_profiles(sim_dir)
    twitter_profiles = _enrich_from_reddit(_load_twitter_profiles(sim_dir), reddit_profiles)
    for platform, profiles in (
        ("twitter", twitter_profiles),
        ("reddit", reddit_profiles),
    ):
        conflicts, text_count = audit_platform(sim_dir, platform, profiles, max_examples)

        total_text_actions += text_count
        total_conflicts += len(conflicts)
        all_conflicts.extend(conflicts)

        by_reason: dict[str, int] = {}
        for c in conflicts:
            by_reason[c.reason] = by_reason.get(c.reason, 0) + 1
            by_reason_total[c.reason] = by_reason_total.get(c.reason, 0) + 1

        rate = len(conflicts) / text_count if text_count > 0 else 0.0
        platform_summaries.append(
            RoleLeakagePlatformSummary(
                platform=platform,
                text_actions=text_count,
                conflicts=len(conflicts),
                rate=rate,
                by_reason=by_reason,
            )
        )

    total_rate = total_conflicts / total_text_actions if total_text_actions > 0 else 0.0

    return RoleLeakageSummary(
        sim_dir=str(sim_dir),
        text_actions=total_text_actions,
        conflicts=total_conflicts,
        rate=total_rate,
        by_reason=by_reason_total,
        per_platform=platform_summaries,
        examples=all_conflicts[:max_examples],
    )
