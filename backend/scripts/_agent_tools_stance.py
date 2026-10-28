"""
Stance, sentiment bias, and persona profile augmentation for agent tools.
"""

import csv
import json
import re
from typing import Dict, Any, List, Optional

# Issue #1713 Slice S6 (Befund 7): stance/sentiment_bias werden pro Agent in
# simulation_config_agents.py erzeugt, erreichten den Agenten-Prompt bisher
# aber nie — Konsens/Echo nach einer Runde. `_describe_stance` formuliert die
# Haltung als Disposition ("du siehst ... kritisch"), nie als Verhaltens-
# vorhersage ("du wirst ... widersprechen").
#
# #1779: Nur noch Seiten tragen eine Tönung ("positiv"/"kritisch"). observer und
# neutral bekamen früher Formeln wie "ohne aktiv Position zu beziehen"; das Modell
# befolgte sie (25 observer + 13 neutral von 54 Agenten ohne Position im Lauf
# sim_c8c6b30aa652). Sie neigen jetzt nach dem Vorzeichen von ``sentiment_bias``.
_STANCE_ATTITUDE = {
    "supportive": "positiv",
    "opposing": "kritisch",
}

#: Ab diesem Betrag zählt ``sentiment_bias`` als Neigung (kleiner: Rauschen).
_LEAN_THRESHOLD = 0.1

#: Lesbare Rollen für die technischen Entitätstypen der Ontologie (CamelCase,
#: englisch). Schlüssel casefold. Unbekannte CamelCase-Typen entfallen im Satz,
#: statt roh im System-Prompt zu stehen.
_ROLE_LABELS_DE = {
    "person": "Einzelperson",
    "organization": "Organisation",
    "company": "Unternehmen",
    "hospital": "Krankenhaus",
    "governmentagency": "Behörde",
    "healthcareprovidergroup": "Gruppe von Leistungserbringern",
    "politicalgroup": "politische Gruppierung",
    "communitygroup": "Gruppe aus der Bevölkerung",
    "mediaoutlet": "Medium",
    "university": "Hochschule",
    "association": "Verband",
    "union": "Gewerkschaft",
    "publicfigure": "Person des öffentlichen Lebens",
    "expert": "Fachperson",
}


def _stance_lean(sentiment_bias: Optional[float]) -> Optional[str]:
    """``"dafür"``/``"dagegen"`` aus dem Vorzeichen von ``sentiment_bias``, sonst ``None``."""
    if sentiment_bias is None or abs(sentiment_bias) < _LEAN_THRESHOLD:
        return None
    return "dafür" if sentiment_bias > 0 else "dagegen"


def _readable_role(agent_role: str) -> str:
    """Rolle für den Haltungssatz: bekannte Entitätstypen auf Deutsch, technische
    CamelCase-Namen ohne Übersetzung entfallen, lesbare Berufe bleiben."""
    role = (agent_role or "").strip()
    if not role:
        return ""
    label = _ROLE_LABELS_DE.get(role.casefold())
    if label:
        return label
    if re.search(r"[a-z][A-Z]", role):
        return ""
    return role


def _describe_stance(
    stance: str,
    sentiment_bias: Optional[float],
    agent_role: str,
    contested_statement: Optional[str] = None,
) -> str:
    """Haltungssatz aus stance/sentiment_bias, gebunden an die eigene Rolle.

    Bewusst ohne fremde Namen/Rollen (Role-Leakage, #1323) und ohne
    Verhaltensvorhersage — beschreibt eine Disposition, kein Ergebnis.

    Hat der Lauf eine Streitfrage (#1778), bezieht sich der Satz auf genau
    diese Aussage statt auf "das Vorhaben": dieselbe Aussage, auf die sich
    Startkonfiguration und Interview beziehen.

    ``observer`` und ``neutral`` (#1779) bekommen keine Verbotsformel; sie neigen
    nach dem Vorzeichen von ``sentiment_bias`` ("neigst eher dafür/dagegen") oder
    sind ohne Vorzeichen noch nicht festgelegt. Die Aufforderung, die Seite
    erkennbar zu machen, steht einmal im Abschnitt (``build_stance_section``).
    """
    bias = sentiment_bias if sentiment_bias is not None else 0.0
    intensity = "sehr " if abs(bias) >= 0.5 else ""
    lean = _stance_lean(sentiment_bias)
    if contested_statement:
        question = f"„{contested_statement}\""
        if stance == "observer":
            if lean:
                return f"Die Streitfrage {question} verfolgst du aufmerksam; du neigst eher {lean}."
            return f"Die Streitfrage {question} verfolgst du aufmerksam; du hast dich noch nicht festgelegt."
        if stance == "supportive":
            return f"Zur Streitfrage {question} bist du {intensity}dafür."
        if stance == "opposing":
            return f"Zur Streitfrage {question} bist du {intensity}dagegen."
        if lean:
            return f"Zur Streitfrage {question} bist du noch nicht festgelegt, neigst aber eher {lean}."
        return f"Zur Streitfrage {question} bist du noch unentschieden."
    # Ohne bekannte Rolle kein Platzhalter wie "als Unknown" im System-Prompt.
    role = _readable_role(agent_role)
    role_clause = (
        f" aus deiner Rolle als {role}"
        if role and role.lower() not in {"unknown", "none", "n/a"}
        else ""
    )
    if stance == "observer":
        if lean:
            return f"Du verfolgst das Geschehen{role_clause} aufmerksam und neigst eher {lean}."
        return f"Du verfolgst das Geschehen{role_clause} aufmerksam und hast dich noch nicht festgelegt."
    if stance not in _STANCE_ATTITUDE:
        if lean:
            return f"Du bist in dieser Frage{role_clause} noch nicht festgelegt, neigst aber eher {lean}."
        return f"Du bist in dieser Frage{role_clause} noch unentschieden."
    attitude = _STANCE_ATTITUDE[stance]
    return f"Du siehst das Vorhaben{role_clause} {intensity}{attitude}."


def _describe_posting_tendency(
    posts_per_hour: Optional[float],
    comments_per_hour: Optional[float],
    stance_bearing: bool = False,
) -> str:
    """Beitragsneigung relativ aus posts_per_hour/comments_per_hour, ohne die
    Rohzahlen aus dem Material wörtlich zu übernehmen.

    ``stance_bearing`` (#1779): Agenten mit Seite oder Neigung werden nicht auf
    Reaktionen festgelegt. Im Lauf sim_c8c6b30aa652 sagte der Satz allen 50
    Personas "eher Reaktionen", und nur 3 von 410 Beiträgen waren eigene — die
    Haltung wurde fast nie unabhängig vom Feed gesetzt.
    """
    if posts_per_hour is None or comments_per_hour is None:
        return ""
    if posts_per_hour <= 0 and comments_per_hour <= 0:
        return ""
    ratio_threshold = 1.3
    if posts_per_hour > comments_per_hour * ratio_threshold:
        return "Du meldest dich eher mit eigenen Beiträgen zu Wort als mit Reaktionen."
    if comments_per_hour > posts_per_hour * ratio_threshold:
        if stance_bearing:
            return (
                "Du antwortest oft auf andere, schreibst aber auch einen eigenen Beitrag, "
                "wenn du etwas Eigenes zur Streitfrage zu sagen hast."
            )
        return "Du meldest dich eher mit Reaktionen auf andere zu Wort als mit eigenen Beiträgen."
    return "Du beteiligst dich etwa gleich häufig mit eigenen Beiträgen wie mit Reaktionen."


def build_stance_section(
    stance: Optional[str],
    sentiment_bias: Optional[float],
    agent_role: str,
    posts_per_hour: Optional[float] = None,
    comments_per_hour: Optional[float] = None,
    contested_statement: Optional[str] = None,
) -> str:
    """Baut den Abschnitt "Deine Haltung" — gemeinsame Quelle für beide Pfade,
    die einen Agenten-Prompt/System-Prompt bauen (#1713 Slice S6):

    - den ReAct-Tool-Prompt (``build_agent_prompt_with_tools``, erreichbar im
      Single-Platform-Runner über ``ToolAwareActionLoop.decide_action``)
    - den Profiltext, den OASIS beim Aufbau des Agent-Graphs in den
      nativen CAMEL-System-Prompt übernimmt (Parallel-Runner,
      ``augment_profile_with_stance``), weil dort ``tool_loop`` seit #1215
      fest auf ``None`` steht und der ReAct-Prompt nie gebaut wird.

    Eine Formulierung statt zweier Kopien — Disposition, keine
    Verhaltensvorhersage, an die eigene Rolle gebunden (Role-Leakage-Schutz,
    #1323). Leerstring, wenn ``stance`` fehlt (Altkonfig): der Aufrufer lässt
    den Abschnitt dann komplett weg statt ihn mit leeren Werten zu füllen.
    """
    if not stance:
        return ""
    stance_sentence = _describe_stance(
        stance, sentiment_bias, agent_role, contested_statement
    )
    stance_bearing = stance in _STANCE_ATTITUDE or _stance_lean(sentiment_bias) is not None
    posting_sentence = _describe_posting_tendency(posts_per_hour, comments_per_hour, stance_bearing)
    return (
        "## Deine Haltung\n"
        f"{stance_sentence}"
        + (f" {posting_sentence}" if posting_sentence else "")
        + "\nReaktionen dürfen zustimmen oder widersprechen, je nachdem was zu "
        "deiner Haltung passt. Mach in deinem Beitrag erkennbar, auf welcher Seite du "
        "stehst oder wohin du neigst. Wiederhole keine Formulierungen aus deiner Bio "
        "oder der Beobachtung wörtlich — ordne Zahlen und Fakten aus deinen "
        "Quellen mit deiner eigenen Einschätzung ein.\n"
    )


def build_stance_anchor(
    stance: Optional[str],
    sentiment_bias: Optional[float],
    agent_role: str,
    contested_statement: Optional[str] = None,
) -> str:
    """Kurze Erinnerung an die eigene Haltung für den Feed-Text jeder Aktivierung (#1779).

    Der Abschnitt "Deine Haltung" steht genau einmal in der System-Nachricht und
    wird im Parallelpfad nie erneuert; über viele Runden verblasst er gegen den
    wachsenden Feed. Dieser Anker wiederholt Streitfrage und eigene Seite in
    einem Absatz am Ende des Feeds (``agent_feed.install_stance_anchor``). Er
    nutzt denselben Haltungssatz wie ``build_stance_section``
    (``_describe_stance``), keine zweite Formulierung. Leerstring ohne ``stance``
    (Altkonfig): dann bleibt der Feed unverändert.
    """
    if not stance:
        return ""
    sentence = _describe_stance(stance, sentiment_bias, agent_role, contested_statement)
    return f"Erinnerung an deine Haltung: {sentence} Lass sie in deinem Beitrag erkennen."


def _profile_prompt_sections(
    platform: str,
    stance_section: str,
    voice_register: Optional[str],
    entity_type: str,
    activity_limits: str = "",
) -> str:
    """Haltung, Beitragslänge und Aktivitätsgrenzen für den Profiltext (Issue #1759, A7).

    ``activity_limits`` (#1779): Satz mit den Grenzen je Aktivierung aus dem
    Aktivitätsmodell; leer in Altkonfigurationen, dann bleibt der Text unverändert.

    Die Längengrenze hängt an Plattform und Voice-Register
    (``persona_post_length``). Trägt das Profil kein Register (Altbestand,
    Twitter-CSV vor #1759), gilt das Register, das die Rolle des Entitätstyps
    vorgibt — dieselbe Zuordnung wie bei der Persona-Erzeugung.
    """
    from app.services.persona_post_length import build_length_section
    from app.services.persona_voice_register import rule_based_voice_register

    register = voice_register or rule_based_voice_register(entity_type)
    limits_section = f"## Deine Aktivität\n{activity_limits}\n" if activity_limits else ""
    return "\n".join(
        part
        for part in (stance_section, build_length_section(platform, register), limits_section)
        if part
    )


def _augment_twitter_csv_with_stance(
    profile_path: str,
    cfg_by_id: Dict[Any, Dict[str, Any]],
    contested_statement: Optional[str] = None,
    activity_limits: str = "",
) -> str:
    """Hängt ``build_stance_section`` an die ``user_char``-Spalte einer Kopie
    von ``twitter_profiles.csv`` an — genau das Feld, das
    ``oasis/social_platform/config/user.py::UserInfo.to_twitter_system_message``
    wörtlich in den System-Prompt jedes Agenten übernimmt."""
    with open(profile_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not fieldnames or "user_char" not in fieldnames:
        return profile_path

    changed = False
    for idx, row in enumerate(rows):
        cfg = cfg_by_id.get(idx, {})
        section = build_stance_section(
            stance=cfg.get("stance"),
            sentiment_bias=cfg.get("sentiment_bias"),
            agent_role=str(cfg.get("entity_type") or ""),
            posts_per_hour=cfg.get("posts_per_hour"),
            comments_per_hour=cfg.get("comments_per_hour"),
            contested_statement=contested_statement,
        )
        section = _profile_prompt_sections(
            "twitter",
            section,
            row.get("voice_register") or cfg.get("voice_register"),
            str(cfg.get("entity_type") or ""),
            activity_limits,
        )
        if section:
            row["user_char"] = f"{row.get('user_char', '')}\n{section}".strip()
            changed = True

    if not changed:
        return profile_path

    out_path = (
        profile_path[: -len(".csv")] + "_with_stance.csv"
        if profile_path.endswith(".csv")
        else profile_path + "_with_stance"
    )
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def _augment_reddit_json_with_stance(
    profile_path: str,
    cfg_by_id: Dict[Any, Dict[str, Any]],
    contested_statement: Optional[str] = None,
    activity_limits: str = "",
) -> str:
    """Hängt ``build_stance_section`` an das ``persona``-Feld einer Kopie von
    ``reddit_profiles.json`` an — genau das Feld, das
    ``oasis/social_platform/config/user.py::UserInfo.to_reddit_system_message``
    wörtlich in den System-Prompt jedes Agenten übernimmt
    (``agents_generator.py::generate_reddit_agent_graph`` liest
    ``agent_info[i]["persona"]``)."""
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    # Issue #1778: Zugriff über die Position, wie im Twitter-Zweig. OASIS
    # nummeriert die Agenten nach der Position des Profils; der Runner übergibt
    # eine darauf umgeschriebene Konfiguration (``align_config_to_profiles``).
    for idx, item in enumerate(data):
        cfg = cfg_by_id.get(idx, {})
        section = build_stance_section(
            stance=cfg.get("stance"),
            sentiment_bias=cfg.get("sentiment_bias"),
            agent_role=str(item.get("profession") or cfg.get("entity_type") or ""),
            posts_per_hour=cfg.get("posts_per_hour"),
            comments_per_hour=cfg.get("comments_per_hour"),
            contested_statement=contested_statement,
        )
        section = _profile_prompt_sections(
            "reddit",
            section,
            item.get("voice_register") or cfg.get("voice_register"),
            str(item.get("source_entity_type") or cfg.get("entity_type") or ""),
            activity_limits,
        )
        if section:
            item["persona"] = f"{item.get('persona', '')}\n{section}".strip()
            changed = True

    if not changed:
        return profile_path

    out_path = (
        profile_path[: -len(".json")] + "_with_stance.json"
        if profile_path.endswith(".json")
        else profile_path + "_with_stance"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


def augment_profile_with_stance(
    profile_path: str,
    agent_configs: List[Dict[str, Any]],
    platform: str,
    contested_statement: Optional[str] = None,
    activity_limits: str = "",
) -> str:
    """Trägt die Haltung aus ``agent_configs`` in eine EIGENE Kopie der
    Profildatei ein, die OASIS beim Aufbau des Agent-Graphs
    (``generate_twitter_agent_graph``/``generate_reddit_agent_graph``) liest.
    """
    if not agent_configs:
        return profile_path

    cfg_by_id = {cfg.get("agent_id"): cfg for cfg in agent_configs}

    if platform == "twitter":
        return _augment_twitter_csv_with_stance(
            profile_path, cfg_by_id, contested_statement, activity_limits
        )
    return _augment_reddit_json_with_stance(
        profile_path, cfg_by_id, contested_statement, activity_limits
    )
