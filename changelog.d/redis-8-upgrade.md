`docker-compose.yml` zieht die Redis-Image-Version von `redis:7-alpine` auf
`redis:8-alpine` nach. `agora-redis` lief produktiv bereits seit dem 18.09.
auf Version 8 (manuell hochgezogen); ohne diesen Commit hätte der nächste
`docker compose up` auf dem Deploy-Host die Version stillschweigend wieder
auf 7 zurückgesetzt.

Kein Anwendungscode geändert.
