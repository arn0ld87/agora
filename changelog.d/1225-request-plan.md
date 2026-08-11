Das Zusammensetzen eines Provider-Requests und das Durchbringen dieses Requests gegen bekannte Provider-400er liegen nicht mehr in `LLMClient.chat`, sondern hinter `build_request` und `execute` im neuen Modul `app/llm/request_plan.py`. `chat` schrumpft von 315 auf 257 Zeilen und behält nur noch, was wirklich dazugehört: Stub-Pfad, Streaming-Reassembly, Budget- und Telemetrie-Buchführung.

Die Quirks stehen damit genau einmal im Code. Bisher standen sie viermal: `chat`, `describe_image` und `tool_calls` hatten je eine eigene Kopie des Request-Shapings, drei davon je eine eigene Fallback-Kaskade. Jede Kopie hatte eine andere Lücke — der Tools-Pfad kennt den `temperature`-Quirk aus #1096 nicht, der Vision-Pfad kennt MiniMax nicht. Diese Lücken bleiben unverändert bestehen, stehen jetzt aber als benannter Seam sichtbar da statt als stiller Unterschied zwischen drei Textstellen.

Was ein Request über seine Umgebung braucht, kommt über `RequestOptions` herein — Provider-Seams mit Default-Bindung an die echten Heuristiken. Ein Test setzt Fakes in die Options und prüft `build_request` und `execute` direkt am Interface, ohne `patch()` auf Modulnamen.

`detect_provider` bleibt Single Source of Truth für die Provider-Erkennung; `request_plan` erkennt nichts selbst, sondern bekommt das Ergebnis übergeben.

Verhalten unverändert — reiner Deepening-Refactor.
