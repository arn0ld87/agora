# 04 — Antwortziele und sichtbarer Kontext (#1835)

Stand: `9cc4afd3`, 2026-10-10. Belegt durch `backend/tests/scripts/test_reply_targets_and_visible_context.py` (offline, synthetische Daten, kein Lauf, kein Provider).

## Kurzfazit

Auf dem nativen Aktionspfad (Parallel-Runner und Einzel-Runner ohne Agent-Tools) erreicht eine Antwort auf einen Kommentar die Plattform als verschachtelter Kommentar; fehlende und fremde Ziele werden abgelehnt, und der Feed nennt `comment_id` und `parent_comment_id` je Kommentar. Der ReAct-Tool-Loop verwirft `parent_comment_id` (und kennt kein Antwortziel im Prompt), ist unter Standardkonfiguration aber kein aktiver Laufpfad. Der Referenzlauf `sim_c56d9430b50a` lief nativ; der Defekt im ReAct-Loop ist dafür kein Kausalnachweis. Im gedeckelten Feed des nativen Pfads zeigen sichtbare Antworten teils auf nicht mehr sichtbare Elternkommentare (D1 größer 0, siehe Messwerte). Gate G1 ist nein: kein Fix, keine Änderung an Produktivcode.

## Laufpfad-Matrix

| Einstieg | `enable_agent_tools` | Aktionspfad | Nested-Patch | Antwort auf Kommentar |
|---|---|---|---|---|
| parallel (Plattform nicht allein twitter/reddit; `process_manager.py:472-479`, Skript `run_parallel_simulation.py`) | ohne Wirkung | nativ (`LLMAction()`, `tool_loop = None` in `run_parallel_simulation.py:1583` und `:1982`; ReAct-Zweige `:1831`, `:2200` unerreichbar) | ja, beim Import (`:191`) | ja |
| reddit ohne Tools (`run_reddit_simulation.py`) | aus (Default, `settings.py:79`, `simulation_config_models.py:172`) | nativ | ja (`run_reddit_simulation.py:106`) | ja |
| reddit mit Tools | an | ReAct (`platform_runner.py:723-735`) | ja | nein, `parent_comment_id` wird verworfen (Test C1) |
| twitter ohne Tools (`run_twitter_simulation.py`) | aus | nativ | nein (Einzel-Runner installiert ihn nicht) | nein (Feld fehlt im Schema) |
| twitter mit Tools | an | ReAct | nein | nein |

Hinweise: Der ReAct-Loop entsteht nur mit Graph-Storage (`create_tool_aware_loop` liefert sonst `None`). ReAct-Runden fallen bei Modellfehler oder fehlender Aktion auf `LLMAction()` zurück. Im Parallel-Prozess wirkt der Patch prozessweit, also auch für Twitter.

## Sichtbarer Kontext je Aktivierung, nativer Pfad

- Einmalige System-Nachricht aus dem Profiltext (im Parallel-Runner um den Haltungsabschnitt ergänzt).
- Je Aktivierung eine Nutzer-Nachricht aus dem Feed-Text: kompaktes JSON, neueste fünf Kommentare je Post (`AGORA_SIM_FEED_MAX_COMMENTS`), `omitted_comments`, `comment_id` und `parent_comment_id` je Kommentar, danach der Haltungsanker (#1779).
- Gedächtnisregeln aus #1772 (`AGORA_SIM_MEMORY_KEEP_FEEDS`, `AGORA_SIM_MEMORY_TOKEN_CAP`) unverändert.

Auszug (synthetisch, gekürzt):

```
After refreshing, you will see some posts: [{"post_id":1,"user_id":1,"content":"PPPP…",
"comments":[{"comment_id":101,"post_id":1,"content":"KKKK…","parent_comment_id":null,…},
{"comment_id":102,"post_id":1,"content":"KKKK…","parent_comment_id":101,…}],"omitted_comments":3}]

[Haltungsanker …]
```

## Sichtbarer Kontext je Aktivierung, ReAct-Loop

- Ein einzelner Prompt ohne System-Nachricht und ohne Gedächtnis (`build_agent_prompt_with_tools`).
- Name, Rolle und Bio sind Ersatzwerte `Agent_<id>`, `Unknown` und leer: eine echte `SocialAgent` hat weder `username` noch `profession` noch `bio` (Test C2, `platform_runner.py:787-789`). Bekannte Lücke: Die Persona erreicht den ReAct-Prompt nicht (gleicher Fehlertyp wie #1224). Nicht behoben (inaktiver Pfad).
- Bio-Schnitt 300, Timeline-Schnitt 1500 (`agent_tools.py:1124`, `:1128`); kein Feld und keine Regel für das Antwortziel.

Auszug (synthetisch, gekürzt):

```
You are Alice, a Analystin.

Bio: Bio

## Current Situation
<untrusted_data source="timeline">
…erste 1500 Zeichen des Feed-Texts…
</untrusted_data>

## Available Actions
You can perform one of these actions: CREATE_COMMENT
…
   - For CREATE_COMMENT, also specify "content" (string) for the comment's content.
```

## Antwortziele

| Pfad | Verhalten | Test |
|---|---|---|
| nativ | Antwort mit `parent_comment_id` landet als verschachtelter Kommentar | A1 `test_native_reply_reaches_platform_as_nested_comment` |
| nativ | fehlende oder fremde Eltern-ID: `success False`, keine neue Zeile | A2 `test_native_reply_with_bad_target_is_rejected` |
| nativ | Feed nennt `comment_id` und `parent_comment_id` | A3 `test_feed_shows_comment_id_and_parent_comment_id` |
| ReAct | Aufbau grün: `post_id` und `content` erreichen `action_args` | C1a `test_react_create_comment_setup_keeps_post_id_and_content` |
| ReAct | `parent_comment_id` fehlt in `action_args` (strikt erwarteter Fehlschlag, `raises=AssertionError`) | C1 `test_react_create_comment_forwards_parent_comment_id` |

## Messwerte

Messung, keine Sollwerte; Grenzen 300, 1500, Kommentardeckel und Gedächtnisgrenzen unverändert (D-04).

- C3 (`test_measure_react_timeline_cut`): synthetischer Feed mit 5 Posts und je 5 Kommentaren (Post 280, Kommentar 200 Zeichen) ist 11.068 Zeichen lang. Der Timeline-Schnitt 1500 zeigt davon 13,6 Prozent und 3 von 25 Kommentar-IDs.
- D1 (`test_measure_native_feed_orphaned_reply_targets`): ein Post mit 8 Kommentaren, Deckel 5. Kettenstruktur: 1 sichtbarer Kommentar zeigt auf einen nicht sichtbaren Elternkommentar; Sternstruktur (alle antworten auf den ersten): 5 von 5.
- Referenzprofil `agora-lauf-20260811-sim_54c1c2a6a875/sim_54c1c2a6a875/reddit_profiles.json` (30 Profile; ermittelt per einmaligem Python-Skript über `len(p["bio"])` und `len(p["persona"])`): `bio` Minimum 99, Median 124, Maximum 145, Anteil über 300 gleich 0 Prozent; `persona` Minimum 1.721, Median 3.489, Maximum 5.444, Anteil über 300 gleich 100 Prozent.

Umgang mit D1: Verwaiste Antwortbezüge im gedeckelten Feed sind eine benannte Lücke des nativen Pfads (Wert größer 0), hier nicht behoben (D-04; eine Änderung an Deckel oder Feed-Auswahl braucht einen Lauf als Beleg) und an den Lead gemeldet.

## Gate

Gate G1: nein

G1(a) trifft zu: Test C1 schlägt an seiner einen Zusicherung fehl (`AssertionError`), der ReAct-Loop reicht `parent_comment_id` nicht weiter. G1(b) trifft nicht zu: `enable_agent_tools` ist in `SimulationParameters` und `AgoraSettings` aus, und der Parallel-Runner weist `tool_loop` ausschließlich `None` zu (Test B3, Konstante `G1B_REACT_LOOP_ACTIVE_BY_DEFAULT = False`). Die Nachtriage im Issue (10.10.2026) hält fest, dass der Referenzlauf nativ lief und der inaktive Tool-Loop nicht zur scheinbaren Behebung gepatcht werden soll. Task 2 (Vertrag, Fix, Changelog-Fragment) entfällt.

## Nicht abgedeckt

1. Bewertung von spezifischer Bezugnahme, Rollenunterschieden, neuen Argumenten und Wiederholung: braucht einen echten Lauf oder das Testgerüst aus #1836; Läufe sind hier untersagt.
2. Aufzeichnung von Prompt- und Feed-Snapshots je Aktivierung in echten Läufen: neue Laufzeit-Instrumentierung (Persistenz, Größe, Datenschutz), kein Fix eines bestätigten Defekts, hängt an #1836. Hier nur Offline-Darstellungen aus synthetischen Daten.
3. Rückwirkender Kontextnachweis für `sim_c56d9430b50a`: nicht möglich, es wurden keine Snapshots aufgezeichnet.
4. ReAct-Loop: Weiterreichen von `parent_comment_id` und Persona-Ersatzwerte bleiben unbehoben (inaktiver Pfad); per Test und Doku festgehalten.
5. Änderung der Grenzen 300 und 1500, des Kommentardeckels und der Gedächtnisgrenzen: nur Messung, eine Änderung braucht einen Lauf als Beleg.
6. Verwaiste Antwortbezüge im gedeckelten Feed des nativen Pfads (D1 größer 0): benannte Lücke, nicht behoben, an den Lead gemeldet.
