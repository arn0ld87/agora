### Changed

- Branch-Overrides (`POST /api/simulation/<id>/branch`) akzeptieren jetzt eine
  kanonische `ai_model_ref` (Provider-Connection + Modell) statt nur des
  bisherigen `llm_model`-Strings. Ein neuer `BranchOverrides`-Contract
  (`backend/app/contracts/branch_request_contract.py`) validiert die
  Overrides serverseitig, prüft eine gesetzte `ai_model_ref` gegen die
  bestehende Routing-SSoT (unbekannte oder deaktivierte Connection → HTTP
  400) und lehnt die Kombination `ai_model_ref` + `llm_model` ab. `llm_model`
  bleibt als deprecated Legacy-Key erhalten. `create_branch` schreibt bei
  gesetzter Referenz zusätzlich `simulation_config["ai_model_ref"]`, das
  Legacy-Anzeigefeld `llm_model` bleibt synchron.
- Replay (`POST /api/runs/<id>/replay`) reicht die volle `AiModelRef` an
  `create_branch` durch statt nur die `model_id` — dieselbe Modell-ID kann
  auf mehreren Provider-Connections liegen, die Branch-Config eines Replays
  verlor bisher die Connection-Bindung.
- Frontend: `ReportBranchControls.vue` sendet die volle Picker-Auswahl mit;
  `Step4Report.vue` schickt die kanonische Referenz, sobald sie noch mit dem
  sichtbaren Modellfeld übereinstimmt, sonst weiterhin den Legacy-String.
