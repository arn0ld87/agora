### Fixed

- Öffentliche Demo: Die Seite „Eigene Anbieter-Keys" bietet alle BYOK-fähigen Anbieter an (zusätzlich Ollama Cloud und Amazon Bedrock) statt fest nur OpenAI, Google Gemini und MiniMax, und liegt in der App-Shell mit Sidebar. Backend-Registry, Key-API, Demo-Bootstrap und Frontend lesen dieselbe Liste (`supported_providers`); ein Betreiber-Bedrock-Token blockiert den Demo-Start (#1688).
