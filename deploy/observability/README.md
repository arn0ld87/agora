# Observability Stack (lokal)

SigNoz Community Edition + OTel-Collector als separater Compose-Stack.

## Start

    docker compose -f docker-compose.observability.yml --profile observability up -d

UI: http://localhost:3301
OTLP-grpc-Endpoint (für Agora-Backend + Frontend): localhost:4317 (grpc), localhost:4318 (http)

## Stop / Reset

    docker compose -f docker-compose.observability.yml --profile observability down
    docker compose -f docker-compose.observability.yml --profile observability down -v  # inkl. Daten
