### Fixed (Simulationsvorbereitung und Gemini-Tool-Turns - 2026-08-12)

- **Prepare läuft pro Simulation exklusiv:** Ein zweiter Start im Zustand `preparing` wird vor Run-, Task- und Artefakterzeugung mit HTTP 409 abgelehnt.
- **Gemini-3-Tool-Historie behält Thought-Signaturen:** Der CAMEL-Adapter übernimmt die Provider-Signatur pro Tool-Call in nachfolgende Assistant-Nachrichten und nutzt den dokumentierten Validator-Ersatz nur für synthetisch rekonstruierte Calls.
