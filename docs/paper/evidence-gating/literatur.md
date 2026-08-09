# Literaturstand — Evidence-Gating-Paper

**Stand:** 07.08.2026, erste Rechercherunde
**Zweck:** Grundlage für Abschnitt 2 (Verwandte Arbeiten) und Prüfung des Neuheitsanspruchs

Jeder Eintrag ist nach Prüftiefe gekennzeichnet — dasselbe Prinzip, das das Paper beschreibt:

- `[volltext]` — PDF oder Abstract-Seite selbst abgerufen und gelesen
- `[abstract]` — nur Kurzfassung gesehen
- `[treffer]` — bisher nur als Suchtreffer bekannt, Inhalt ungeprüft

Alle Einträge sind frei verfügbar (arXiv oder ACL Anthology). **Bibliothekszugang wird für keinen davon gebraucht.**

---

## A. Zuerst lesen

### A1. Attribution, Citation, and Quotation: A Survey of Evidence-based Text Generation with LLMs `[abstract]`

Tobias Schreieder, Tim Schopf, Michael Färber. ACL 2026. arXiv:2508.15396
<https://arxiv.org/abs/2508.15396>

Survey über 134 Arbeiten mit 300 Evaluationsmetriken in sieben Dimensionen. Deckt exakt das Feld ab, in dem sich das Paper verorten muss.

**Das ist die wichtigste Quelle der ganzen Liste.** Wer sie gelesen hat, weiß, ob der Neuheitsanspruch trägt. Bis dahin ist jede Aussage über Neuheit vorläufig.

Zusätzlich relevant: **Michael Färber ist seit April 2024 W3-Professor bei ScaDS.AI Dresden/Leipzig** und leitet dort „Scalable Software Architectures for Data Analytics". Sein Schwerpunkt ist vertrauenswürdige KI an der Schnittstelle von LLMs, Knowledge Graphs und strukturierter Wissensrepräsentation. Das ist Agoras exakte Kombination. Siehe Abschnitt D.

---

## B. Nächstliegende Arbeiten — hier entscheidet sich die Abgrenzung

### B1. Contradiction to Consensus: Dual Perspective, Multi Source Retrieval Based Claim Verification with Source Level Disagreement `[volltext]`

arXiv:2602.18693 · <https://arxiv.org/pdf/2602.18693>

Ruft Belege aus mehreren Quellen ab, modelliert ausdrücklich Fälle, in denen Quellen einander widersprechen, und lässt diese Uneinigkeit in die Konfidenzbewertung einfließen.

**Die inhaltlich nächste Arbeit — und damit die gefährlichste.** Unterschiede zu Evidence-Gating, soweit bisher geprüft: es geht um Verifikation *vorgelegter* Behauptungen gegen Wikipedia, nicht um Berichterzeugung; die Quellen sind abgerufene Dokumente, nicht simulierte Stakeholder-Gruppen; der Mechanismus ist hybrid aus Heuristik und LLM, keine harte Typregel.

Diese Abgrenzung muss im Paper explizit und fair stehen. Sie darf nicht so klingen, als hätte man die Arbeit kleingeredet.

### B2. MaRGen: Multi-Agent LLM Approach for Self-Directed Market Research and Analysis `[abstract]`

Roman Koshkin, Pengyu Dai, Nozomi Fujikawa, Masahito Togami, Marco Visentini-Scarzanella. 2025. arXiv:2508.01370
<https://arxiv.org/abs/2508.01370>

Multi-Agenten-System (Researcher, Reviewer, Writer, Retriever), das eigenständig Marktforschungsberichte erzeugt. Lernt per In-Context-Learning aus echten Beratermaterialien bei Amazon.

**Thematisch die nächste Arbeit an Agora überhaupt** — und laut Abstract *ohne* Provenienzmodell und *ohne* Konfidenzvergabe. Das ist die belegbarste Lücke, die die Recherche bisher hergibt: Multi-Agenten-Berichtserzeugung existiert, aber ohne Evidenzstufen. Vor Verwendung im Volltext nachprüfen.

### B3. When LLMs Agree, Are They Right? Auditing Self-Consistency and Cross-Model Agreement as Confidence Signals `[treffer]`

arXiv:2607.08065 · <https://arxiv.org/html/2607.08065v1>

Untersucht Übereinstimmung zwischen Modellen als Konfidenzsignal, mit dem Ergebnis, dass Selbstkonsistenz nur bedingt als Korrektheitsproxy taugt und Frontier-Modelle trotz Fehlern überkonfident übereinstimmen.

Wichtig für die Abgrenzung: Dort geht es um Übereinstimmung *zwischen Modellen*, bei Agora um Übereinstimmung *zwischen Stakeholder-Perspektiven*. Der Befund ist zugleich ein Argument für den eigenen Ansatz — Konsens allein trägt keine Konfidenz, es kommt darauf an, *wessen* Konsens.

---

## C. Feldkontext

### C1. ALCE — Automatic LLMs' Citation Evaluation `[treffer]`

Erster Benchmark für automatische Zitationsbewertung, mit Metriken für Zitationsqualität (Recall/Precision), Korrektheit und Flüssigkeit. Datensätze ASQA, ELI5, QAMPARI.

Standardreferenz für „wie misst man Attribution". Über den Survey A1 auffindbar; exakte Zitation von dort übernehmen.

### C2. RARR — Retrofit Attribution using Research and Revision `[treffer]`

Erkennt unbelegte Behauptungen in erzeugten Antworten und überarbeitet sie anhand abgerufener Dokumente.

Der gegenteilige Ansatz: nachträgliche Korrektur statt vorheriger Sperre. Gute Kontrastfolie für Abschnitt 4.

### C3. Guardrails, Constrained Decoding, Structured Output `[treffer]`

Guardrails AI, NVIDIA NeMo Guardrails, Grammar-Constrained Decoding.

**Wichtig für die Ehrlichkeit des Papers:** Schema-Erzwingung von LLM-Ausgaben per JSON-Schema oder Pydantic ist etablierte Praxis, kein Beitrag. Der Beitrag kann nur in der *inhaltlichen Regel* liegen, die auf dieser Ebene durchgesetzt wird — nicht darin, dass überhaupt validiert wird. Dieser Absatz gehört ins Paper, nicht weggelassen.

### C4. LLM-FACETS `[treffer]`

arXiv:2605.31167

Färbt erzeugten Text nach fünf Konfidenzstufen auf Basis von Token-Logprobs ein.

Kontrast: Konfidenz aus Modellinterna gegenüber Konfidenz aus Evidenzstruktur. Zwei grundverschiedene Antworten auf dieselbe Frage.

---

## D. Erste Bilanz zum Neuheitsanspruch

Der ursprüngliche Anspruch war zu breit. Was **nicht** neu ist:

- Aussagen auf Quellen zurückführen — großes, gut bearbeitetes Feld (A1)
- LLM-Ausgaben per Schema validieren — Industriestandard (C3)
- Quellendiversität und Quellenuneinigkeit als Konfidenzsignal — existiert in der Fact-Checking-Domäne (B1)
- Multi-Agenten-Systeme für Berichtserzeugung — existiert (B2)

Was nach dieser Runde als möglicher Beitrag übrig bleibt, deutlich enger gefasst:

> Eine **inhaltliche Diversitätsanforderung** — Belege aus mindestens zwei verschiedenen Stakeholder-Gruppen — die als **harte Typregel in der Ausgabevalidierung** durchgesetzt wird, angewandt auf **Berichte aus simulierten Agenten** statt aus abgerufenen Dokumenten.

Belastbar wird das erst nach Lektüre von A1 und B2 im Volltext. Fällt dabei auf, dass es das schon gibt, ist das kein Verlust: Dann wird das Paper ein *Erfahrungsbericht* über die Umsetzung bekannter Prinzipien in einem konkreten System — auch das ist publizierbar, nur mit anderem Titel und ohne Neuheitsanspruch.

---

## E. Nebenbefund für die ScaDS.AI-Anfrage

Der Erstkontakt sollte überdacht werden. Die allgemeine Transferstelle war die Empfehlung ohne dieses Wissen — inzwischen gibt es eine deutlich präzisere Adresse:

**Prof. Dr.-Ing. Michael Färber**, ScaDS.AI Dresden/Leipzig, Professur für Skalierbare Software-Architekturen für Data Analytics. Mitautor von A1, also des aktuellen Überblicks über genau das Feld, in dem Agora sich bewegt. Forschungsschwerpunkt LLMs plus Knowledge Graphs plus vertrauenswürdige KI.

Eine Mail an jemanden, dessen Survey man gelesen hat und auf dessen Taxonomie man sich bezieht, ist etwas völlig anderes als eine allgemeine Kooperationsanfrage. Sie setzt allerdings voraus, dass A1 tatsächlich gelesen wurde — sonst fällt sie beim ersten Rückfragesatz auseinander.

Reihenfolge daraus: **erst A1 lesen, dann Mail, dann Paper.**
