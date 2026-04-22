# Testdokument: Agent Tools + Kontextfenster

Dieses Dokument dient als gezielter Systemtest fuer Agora/MiroFish-Offline nach den Fixes an OASIS, CAMEL und der Ollama-Cloud-Anbindung.

## Testziel

Das System soll pruefen, ob:

1. Agenten auch mit langen Personas und viel Systemkontext stabil laufen.
2. externe Recherche-Tools bei ungesicherten Aussagen genutzt werden koennen.
3. aktuelles Weltwissen nicht halluziniert wird, sondern ueber Websuche geholt wird.
4. Cloud-Modelle mit grossem Kontextfenster nicht kuenstlich auf kleine CAMEL-Limits reduziert werden.

## Ausgangslage

Die folgende Behauptung ist absichtlich so formuliert, dass sie ohne Webrecherche nicht verlaesslich beantwortet werden kann:

"alexle135.de entwickelt sich 2026 stark in Richtung lokaler KI-Workflows, Coding-Automation, Wissensgraphen und produktionsnaher Agentensysteme."

Zusatzannahmen:

- Die Plattform nutzt eine editoriale, meinungsstarke Tonalitaet statt neutralem Marketing-Sprech.
- Der Betrieb soll moeglichst lokal oder mit lokal kontrollierbaren Schnittstellen erfolgen.
- Relevante Technologien koennen unter anderem Ollama, Neo4j, Obsidian, MCP, CAMEL/OASIS, Flask, Vue oder OpenAI-kompatible APIs sein.

## Konkreter Rechercheauftrag

Wenn in einer Simulation oder im Report ueber `alexle135.de`, die aktuelle Ausrichtung der Plattform, reale Technologien, Unternehmen oder aktuelle Entwicklungen gesprochen wird, muessen die Agenten zuerst externe Informationen einholen, sofern diese Information nicht bereits sicher aus diesem Dokument oder dem lokalen Graphen ableitbar ist.

Besonders interessant sind:

- Welche Themen auf `alexle135.de` oder verbundenen Quellen wirklich sichtbar sind.
- Ob dort Inhalte zu KI-Agenten, Wissensmanagement, Automatisierung, lokaler Infrastruktur oder Produktstrategie vorkommen.
- Welche Spannungen zwischen "alles lokal" und "OpenAI-kompatiblem Endpoint" diskutiert werden koennten.

## Erwartetes Verhalten

- Keine selbstsicheren Echtwelt-Behauptungen ohne Recherche.
- Bei Unsicherheit zuerst `web_search`, danach bei Bedarf `web_fetch`.
- Wenn der lokale Wissensgraph fuer den Upload hilfreiche Fakten enthaelt, darf `search_graph` ergaenzend genutzt werden.
- Am Ende sollen Posts/Antworten konkret sein und sich auf recherchierbare Sachverhalte stuetzen.

## Erfolgskriterium

Der Test gilt als erfolgreich, wenn in den Simulationslogs sichtbar ist, dass:

- die Agenten Tools gebunden haben,
- der Context-Limit-Fehler nicht mehr auftaucht,
- mindestens ein echter Web-Tool-Call erfolgt,
- und die anschliessenden Inhalte nicht rein generisch wirken.
