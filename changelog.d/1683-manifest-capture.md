### Fixed

- Das Draft-Manifest eines Simulationsstarts trug `seed_document_hash`/
  `seed_document_filename="unknown"` und ein leeres `prompts.entries` (Issue
  #1683, Teil von #1274) — beide Platzhalter, unabhängig davon, ob die
  echten Werte verfügbar waren. `_capture_start_manifest_draft` liest jetzt
  den rohen Projekt-Quelltext (`ProjectManager.get_extracted_text`) und
  hasht ihn per SHA-256, plus die Original-Dateinamen aus dem
  Dokument-Manifest (ADR-0013); ist die Quelle wirklich nicht ermittelbar,
  bleibt das Feld `None` statt `"unknown"`. `prompts.entries` enthält jetzt
  einen byte-genauen Snapshot des tatsächlich verwendeten Prompt-Templates
  der `simulation_rounds`-Stage: `oasis.social_platform.config.user.
  UserInfo.to_system_message` aus der gepinnten `camel-oasis`-Dependency —
  Agora übergibt kein eigenes `user_info_template`, das
  Standardverhalten der Dependency bestimmt den Prompt-Inhalt vollständig.
  Die Pfadauflösung läuft über `importlib.metadata` statt eines echten
  `import oasis`, damit der Webprozess nicht Torch/Sentence-Transformers
  lädt, die OASIS sonst nur im separaten Simulations-Subprozess braucht.
