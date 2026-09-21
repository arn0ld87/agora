### Added (Decision-Provider-Port für den Jev-Piloten — 2026-09-21)

- **`DecisionProvider`-Port mit Rule-/Fake-/LLM-Referenzadaptern:** `backend/app/repositories/decision_provider.py` definiert den Port, `backend/app/services/decisions/` liefert die drei Referenzadapter. `Config.DECISION_LAYER_MODE` (`disabled`/`shadow`/`authoritative`) steuert zentral, ob der Decision Layer für den Piloten überhaupt aktiv ist; Flag-off (Default) lässt den bestehenden Pfad unverändert. (f005, ADR-0016/0017)
