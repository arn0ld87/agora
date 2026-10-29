### Fixed

- **PR-Backend-Gate scheiterte unter `pytest-xdist` an `FileExistsError: './log'` (29.10.2026).** OASIS legt beim Import `./log` ohne `exist_ok` an. Seit dem xdist-Gate (#1898) und dem Import in `tests/unit/test_platform_runner_parity.py` (#1897) importieren mehrere Worker OASIS gleichzeitig während der Collection; der langsamere scheiterte. Die Root-Conftest legt das Verzeichnis jetzt einmal im Controller an, bevor die Worker starten. `backend/log/` steht in `.gitignore`. Nur Test-Infrastruktur, das Image ist nicht betroffen.
