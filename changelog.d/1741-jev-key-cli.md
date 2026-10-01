### Added

- `backend/scripts/bind_decision_secret.py` bindet bzw. entfernt den
  Jev-API-Key (TypeSafe, Ref `jev`) im bestehenden verschlüsselten
  Provider-Secret-Store, über eine feste Allowlist statt der freien
  `provider_id` von `llm-secrets-doctor.py`. Der Key wird ausschließlich
  über stdin gelesen, nie als CLI-Argument. Runbook:
  `docs/runbooks/decision-secrets.md`.

### Fixed

- Das Skript überschreibt jetzt keinen bestehenden Store-Eintrag mehr,
  wenn der aktuelle `AGORA_SECRET_KEY` nicht zum vorhandenen Store-Inhalt
  passt (Exit-Code 2 statt stillem Datenverlust): ein syntaktisch
  gültiger, aber falscher Master-Key hätte zuvor einen vorhandenen
  Ciphertext klaglos überschrieben, und der Roundtrip-Check hätte das
  fälschlich bestätigt — der Verlust wäre erst nach einer späteren
  Korrektur der Umgebung sichtbar geworden.
