"""Integration-Job setzt jede Umgebung, die die Integrations-Fixtures lesen (Issue #1577).

Der Job ``integration`` in ``.github/workflows/ci.yml`` setzt
``AGORA_TEST_REQUIRE_SERVICES=1``. Damit wird jede fehlende
``AGORA_TEST_*``-Variable in ``tests/integration/conftest.py`` zu einem harten
Fail statt zu einem Skip — gewollt, damit ein Integrationsjob nicht gruen wird,
ohne etwas geprueft zu haben.

Genau das ist passiert: die PostgreSQL-Fixture (``AGORA_TEST_POSTGRES_URL``)
kam mit den PostgreSQL-Adaptern (#1517, #1522) dazu, der Job bekam weder den
Service noch die Variable. Er lief auf ``main`` seitdem rot, und die
PostgreSQL-Integrationstests liefen nirgends automatisch.

Der Test liegt in ``tests/contracts/``, weil nur dieses Verzeichnis im
verpflichtenden PR-Gate laeuft — der Integration-Job selbst laeuft erst nach
dem Merge auf ``main``, zu spaet fuer diese Pruefung. Rohtext-Parser ohne
YAML-Bibliothek, aus demselben Grund wie ``test_ci_gate_parity.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
INTEGRATION_DIR = REPO_ROOT / "backend" / "tests" / "integration"

_ENV_NAME = re.compile(r"\bAGORA_TEST_[A-Z0-9_]*[A-Z0-9]\b")
_TOP_LEVEL_JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
_ENV_KEY = re.compile(r"^      (AGORA_TEST_[A-Z0-9_]+):\s*\S")


def _job_block(workflow_text: str, job_name: str) -> list[str]:
    lines = workflow_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = _TOP_LEVEL_JOB.match(line)
        if match and match.group(1) == job_name:
            start = index + 1
            break
    assert start is not None, f"Job '{job_name}' fehlt in {CI_WORKFLOW}"

    block: list[str] = []
    for line in lines[start:]:
        if _TOP_LEVEL_JOB.match(line) or (line and not line.startswith(" ")):
            break
        block.append(line)
    return block


def _job_env_names(job_lines: list[str]) -> set[str]:
    """Liest nur die Job-Ebene ``env:`` (6 Leerzeichen Einrueckung der Keys)."""
    names: set[str] = set()
    in_env = False
    for line in job_lines:
        if line == "    env:":
            in_env = True
            continue
        if in_env:
            if line.startswith("      ") or not line.strip() or line.lstrip().startswith("#"):
                match = _ENV_KEY.match(line)
                if match:
                    names.add(match.group(1))
                continue
            in_env = False
    return names


def _names_read_by_integration_tests() -> set[str]:
    names: set[str] = set()
    for path in INTEGRATION_DIR.glob("*.py"):
        names.update(_ENV_NAME.findall(path.read_text(encoding="utf-8")))
    return names


def test_integration_job_sets_every_env_the_fixtures_read() -> None:
    job_env = _job_env_names(_job_block(CI_WORKFLOW.read_text(encoding="utf-8"), "integration"))
    required = _names_read_by_integration_tests()

    missing = sorted(required - job_env)
    assert not missing, (
        "Der CI-Job 'integration' setzt AGORA_TEST_REQUIRE_SERVICES=1, aber nicht "
        f"{missing}. Die zugehoerigen Integrationstests failen dort hart. "
        "Variable und passenden Service-Container in .github/workflows/ci.yml ergaenzen."
    )


def test_integration_job_starts_a_postgres_service() -> None:
    job_text = "\n".join(_job_block(CI_WORKFLOW.read_text(encoding="utf-8"), "integration"))
    services = job_text.split("    services:", 1)
    assert len(services) == 2, "Job 'integration' hat keinen services-Block"
    assert re.search(r"^      postgres:\s*$", services[1], re.MULTILINE), (
        "AGORA_TEST_POSTGRES_URL ohne PostgreSQL-Service zeigt ins Leere"
    )
    assert re.search(r"image:\s*postgres:17\b", services[1]), (
        "PostgreSQL-Service muss die Hauptversion des Supabase-Stacks (17) nutzen"
    )


def test_the_parser_sees_the_known_variables() -> None:
    """Selbsttest: ein leerer Parser liesse den ersten Test trivial gruen werden."""
    required = _names_read_by_integration_tests()
    assert {"AGORA_TEST_REDIS_URL", "AGORA_TEST_POSTGRES_URL", "AGORA_TEST_REQUIRE_SERVICES"} <= required
    job_env = _job_env_names(_job_block(CI_WORKFLOW.read_text(encoding="utf-8"), "integration"))
    assert "AGORA_TEST_NEO4J_URI" in job_env
