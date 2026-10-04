### Fixed

- Evidence: Claim-Atomizer, Entailment und Fließtext-Prüfung teilen jetzt einen
  Satzsplitter (`services/sentence_splitter.py`), der Ordinal- und Datumsangaben
  nicht mehr zerreißt. „… zum 30. Juni 2027 aufgibt." wurde bisher zu
  „… zum 30." und „Juni 2027 aufgibt."; beide Fragmente landeten als
  Hypothesen, Ledger-Fakten und Data Gaps (#1766).
- Evidence: Bindung, Entailment und Data-Gap-Prüfung lesen dieselbe
  Textprojektion (`services/evidence_text.py`) mit der vollen Interviewantwort
  aus `raw["response"]`. Bisher sahen sie nur das auf 300 Zeichen gekürzte
  Snippet; eine Aussage hinter Zeichen 300 hatte keinen Bindungskandidaten und
  wurde als Datenlücke geführt, obwohl sie in der Quelle stand. Bei Texten über
  600 Zeichen bildet das Retrieval den Score über Satzfenster (drei Sätze, höchstens
  zwölf je Item) statt über den verdünnten Gesamttext; die Kandidaten-Vorauswahl
  nutzt denselben Score (#1766).
