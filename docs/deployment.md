# Deployment

**Stand:** 2026-05-07, Europe/Berlin

Diese Datei ist der Einstieg fuer Deployment-Fragen. Die Detaildokumentation
bleibt bewusst aufgeteilt:

- [`deployment-dev.md`](deployment-dev.md) — lokale Entwicklung, Hot-Reload,
  Dev-Compose.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Single-User-/
  Tailnet-Deployment mit Gunicorn, Reverse-Proxy, Token-Pflicht und
  read-only Runtime-Container.

## Prod-Runtime-Parameter

Die folgenden Compose-Werte sind fuer v1.0 bewusst ueber `.env`
parametrierbar, damit Operatoren keine Compose-Dateien patchen muessen:

| Variable | Default | Zweck |
|---|---|---|
| `AGORA_DNS_PRIMARY` | `8.8.8.8` | Primaerer DNS-Resolver fuer Container. |
| `AGORA_DNS_SECONDARY` | `8.8.4.4` | Sekundaerer DNS-Resolver fuer Container. |
| `NEO4J_IMAGE` | `neo4j:5.18-community` | Neo4j-Image-Pin fuer den Compose-Service. |
| `NEO4J_HEAP_INITIAL` | `512m` | Initiale Neo4j-Heap-Groesse. |
| `NEO4J_HEAP_MAX` | `2g` | Maximale Neo4j-Heap-Groesse. |
| `NEO4J_PAGECACHE_SIZE` | `4g` | Neo4j-Pagecache-Groesse. |

Weitere Prod-Hinweise, inklusive Reverse-Proxy-Smoke und Runtime-Hardening,
stehen in [`deployment-prod-like.md`](deployment-prod-like.md).
