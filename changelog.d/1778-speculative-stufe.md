### Changed

- `ConfidenceLabel` im Report-Contract kennt die fünfte Stufe `speculative`
  unterhalb von `low`; Confidence-Rechner, ReportV3-Vertrag, Prompt-Block und
  Frontend kannten die Stufe bereits, nur das Enum lehnte sie ab. Claims mit
  Scores unter 0,45 behalten jetzt ihr `speculative`-Label, statt nachträglich
  auf `low` gesetzt zu werden und das Degradationsprotokoll zu füllen (#1778).
