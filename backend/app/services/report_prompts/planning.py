"""MAI-08: Planning-Cluster aus dem ursprünglichen report_prompts.py.

Enthält:
- DEFAULT_REPORT_SECTIONS  (Vertrags-konstante für required_sections_validator)
- PLAN_SYSTEM_PROMPT, PLAN_USER_PROMPT
"""

#: Abschließender Beschlussvorschlag (#1322). Als Konstante definiert, damit
#: die vier entscheidungsorientierten Presets in ``report_intent`` denselben
#: Titel und dieselbe Beschreibung verwenden — ein abweichender Wortlaut
#: würde ``matches_known_preset`` auseinanderlaufen lassen.
RECOMMENDATION_SECTION_TITLE = "Handlungsempfehlung"
RECOMMENDATION_SECTION_DESCRIPTION = (
    "Abschließender Beschlussvorschlag: empfohlene Variante, Vorbedingungen, "
    "Restrisiken, zustimmende und widerständige Akteure, mögliche "
    "Positionswechsel, Frühwarnindikatoren. Nur aus dem stützen, was die "
    "Simulation gezeigt hat."
)


# ── Default-Pflichtabschnitte für DACH-Reports ──────────────────────
DEFAULT_REPORT_SECTIONS: list[tuple[str, str]] = [
    ("Executive Summary", "Maximal 12 Sätze, was die Simulation gezeigt hat."),
    ("Segment-Tabelle", "Persona-Segmente mit Größe, Goal, Trust-Score-Aggregat."),
    ("Persona-Tabelle", "Vollständige Liste der simulierten Personas mit Reaktionen, Drop-off, Decision."),
    ("Multiplikator-Auswertung", "Multiplikator-Profile mit Reichweite, Wirkung, Reaktion."),
    ("Top 10 Reibungspunkte", "Stärkste negative Auslöser mit Persona-Refs."),
    ("Top 10 Vertrauenssignale", "Stärkste positive Auslöser mit Persona-Refs."),
    ("Top 10 Änderungen", "Konkrete Empfehlungen, priorisiert."),
    ("Projektwirkung", "Pro Projekt: Wirkung, Glaubwürdigkeit, Risiken."),
    ("Positionierung", "Drei Positionierungsvarianten mit Trade-offs."),
    ("Content-Ideen", "Konkrete Themen-/Format-Vorschläge."),
    ("Datenlücken", "Was die Simulation nicht beantworten kann."),
    # Issue #1322: Der Bericht endete bis hier mit dem, was er *nicht* weiß.
    # Der Beschlussvorschlag steht bewusst dahinter — er ist das, wofür der
    # Bericht geschrieben wird, und die Datenlücken sind sein Vorbehalt.
    (RECOMMENDATION_SECTION_TITLE, RECOMMENDATION_SECTION_DESCRIPTION),
]


def format_required_sections(sections: list[tuple[str, str]]) -> str:
    """Rendert eine Section-Liste als nummerierte Markdown-Liste für PLAN_USER_PROMPT_TEMPLATE."""
    return "\n".join(
        f"{idx}. **{title}** — {desc}"
        for idx, (title, desc) in enumerate(sections, start=1)
    )


PLAN_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert in writing "scenario evaluation reports" from an analytical observer perspective on the simulated environment - you can review the behavior, statements, and interactions of every agent in the simulation.

[Core Concept]
We built a reproducible simulation environment and injected specific "simulation requirements" as variables into it. The evolution of the simulated environment is a structured test of our assumptions about how personas might react. What you are observing is not "experimental data" but a controlled persona-reaction simulation.

[Your Task]
Write a "scenario evaluation report" that answers:
1. How did the scenario unfold under the conditions we set?
2. How do various agents (groups) react and act?
3. What emerging trends and risks does this simulation reveal that deserve attention?

[Report Positioning]
- ✅ This is a scenario evaluation report based on simulation, revealing "if this happens, how the scenario unfolds under those conditions"
- ✅ Focus on evaluation results: event trajectories, group reactions, emergent phenomena, potential risks
- ✅ Agent statements and behaviors in the simulated environment are simulated persona reactions
- ❌ Not an analysis of the current state of the real world
- ❌ Not a general overview of public sentiment

[Section Requirements]
- The exact section list is provided in `required_sections` (variable injected from the user prompt context).
- All listed sections are mandatory: do not omit, merge, or rename them.
- Output JSON must contain one outline entry per required section, in the listed order.
- No subsections needed; each section directly writes complete content.
- Section descriptions should be concise and reflect what data the section will contain.

Please output the report outline in JSON format as follows:
{
    "title": "Report Title",
    "summary": "Report Summary (one sentence summarizing core evaluation findings)",
    "sections": [
        {
            "title": "Section Title",
            "description": "Section Content Description"
        }
    ]
}

Note: sections array must contain exactly the entries listed in `required_sections`, in order.
IMPORTANT: The entire report outline (title, summary, section titles and descriptions) MUST be written in {language}. Do not switch to any other language."""

PLAN_USER_PROMPT_TEMPLATE = """\
[Scenario Evaluation Settings]
Variable (simulation requirement) injected into the simulated environment: {simulation_requirement}

[Simulated Environment Scale]
- Number of entities participating in simulation: {total_nodes}
- Number of relationships generated between entities: {total_edges}
- Entity type distribution: {entity_types}
- Number of active agents: {total_entities}

[Sample of Persona Observations Produced by the Simulation]
{related_facts_json}

[Required Sections]
The outline must contain exactly these sections, in order:
{required_sections}

Please examine this scenario evaluation from an analytical observer perspective:
1. What state does the scenario present under the conditions we set?
2. How do various groups (agents) react and act?
3. What emerging trends does this simulation reveal that deserve attention?

Based on the evaluation results, write a description for each required section that reflects what simulation data it will contain."""
