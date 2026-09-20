Neuer LLM-Provider `claude_cli`: spricht die lokal installierte Claude-Code-CLI
per Subprozess an (Claude-Abo statt Pay-per-Token-API), analog zum
bestehenden `codex_cli`-Provider (ChatGPT-Abo).

Anders als `codex_cli` authentifiziert `claude_cli` über einen mit
`claude setup-token` erzeugten Langzeit-Token (Env-Var
`CLAUDE_CODE_OAUTH_TOKEN`, offiziell für CI/Headless-Nutzung dokumentiert)
statt einer gemounteten Login-Session — der Token liegt wie jeder andere
API-Key im bestehenden Fernet-Secret-Store, es ist kein
Verzeichnis-Mount/Compose-Override nötig.

Jeder Aufruf läuft mit isoliertem `HOME` und `cwd`: ohne diese Isolation lädt
die CLI das komplette interaktive Setup des Hosts (CLAUDE.md, Skills,
Plugins) in den Prompt-Cache — gemessen ~64x höhere Kosten für denselben
Prompt (189.466 vs. 2.935 `cache_creation_input_tokens`). `--tools ""` nimmt
der CLI zusätzlich jeden Werkzeugzugriff; Function-Calling für OASIS-Agenten
läuft wie bei `codex_cli` über eine Prompt-basierte `<tool_call>`-Übersetzung.

Der `claude`-Binary wird im Docker-Image über den offiziellen Installer
(`curl https://claude.ai/install.sh`, Version gepinnt) installiert — der
Installer verifiziert die Downloads intern gegen ein von Anthropic
signiertes Checksummen-Manifest.

Neu: `backend/app/llm/providers/claude_cli.py`,
`backend/scripts/sim_runtime/claude_cli_model.py` (OASIS-Subprozess-Backend).
Geändert: Provider-Registry, Provider-Connections-Adapter, `LLMClient`-Routing,
`Dockerfile`, sowie alle Stellen, die bisher `codex_cli` als einzigen
`transport="cli"`-Provider hartkodiert hatten
(`llm_routing_seed`, `prepare_llm`, `simulation_config_generator`,
`oasis_profile_generator`, `tool_calls`).
