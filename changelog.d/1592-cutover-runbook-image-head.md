### Changed

- **Cutover-Runbook: Image-Head vor der Migration prüfen** — `docs/runbooks/metadata-postgres-cutover.md` verlangt jetzt, dass das laufende Agora-Image denselben Alembic-Head kennt wie der Checkout, bevor `alembic upgrade head` läuft. Beim Cutover auf armserver hatte ein älteres Image nach dem Umschalten am Start-Gate abgebrochen. (#1592)
