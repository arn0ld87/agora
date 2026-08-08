"""CI-Gate-Parity-Guard (Issue #881).

Das verpflichtende CI-PR-Gate (`backend-pr-gate` in `.github/workflows/ci.yml`,
laeuft auf jedem PR) und das lokale Pre-Push-Gate (`scripts/pre-push-gate.sh`,
`run_backend()`) mussten denselben Ruff-Scope pruefen — taten es aber nicht:
CI lintete nur `app/`, das lokale Gate strenger `app/ tests/`.

Konkret geschehen: PR #859 (`bf80dd09`) brachte
`backend/tests/scripts/test_bert_memory_profile.py` mit 6 Ruff-Verstoessen
(2x F401, 4x E101) nach `main`. CI war gruen, weil das PR-Gate nur `app/`
lintete. Auf `main` war `uv run ruff check app/ tests/` seitdem rot,
`pre-push-gate.sh backend` brach jedem lokalen Backend-Slice am ersten
Schritt weg — aufgefallen erst, als ein Worker an Issue #868 daran
haengenblieb. Behoben in PR #879, die Scope-Divergenz selbst blieb offen.

Dieser Test liegt bewusst in `tests/contracts/`, weil genau dieses
Verzeichnis im verpflichtenden PR-Gate laeuft
(`uv run pytest tests/contracts/ -q`) — nur dort wirkt er als Gate und
verhindert, dass der Scope erneut auseinanderlaeuft oder ein Lint-Verstoss
unter `backend/tests/` wieder unbemerkt nach `main` durchrutscht.

Geschuetzt wird die **Definition des Jobs `backend-pr-gate` als Ganzes**,
nicht nur die Ruff-Zeile: der dritte Testfall pinnt zusaetzlich die
Step-Reihenfolge aus PR #884 (`sync-status.sh --check` nach den
Contract-Tests). Beides sitzt in derselben Job-Definition, die dieser PR
anfasst — ein Guard, der nur die Ruff-Zeile kennt, liesse eine zweite
Divergenz im selben Job unbemerkt entstehen.

Reiner Rohtext-Parser fuer `.github/workflows/ci.yml`, keine YAML-Bibliothek:
`pyyaml` ist im gesamten Repo keine deklarierte Dependency (weder in
`[project].dependencies` noch `[project.optional-dependencies].dev` noch in
`[dependency-groups].dev` von `backend/pyproject.toml`) — sie kaeme rein
transitiv ueber `huggingface-hub`/`transformers`/`jsonschema-path`/
`pre-commit` herein. Ein Test im verpflichtenden PR-Gate darf keine
versteckte, jederzeit lautlos entfernbare transitive Kopplung eingehen. Die
Konvention dafuer existiert bereits: `tests/dependencies/test_dependency_ssot.py`
parst CI-Workflows ebenfalls per Regex/Rohtext mit ausschliesslich stdlib
(`re`, `tomllib`, `pathlib`).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRE_PUSH_GATE_PATH = REPO_ROOT / "scripts" / "pre-push-gate.sh"

BACKEND_PR_GATE_JOB = "backend-pr-gate"
RUFF_STEP_NAME = "Ruff lint"
PYTEST_CONTRACTS_STEP_NAME = "Pytest contracts (fast subset)"
SYNC_STATUS_MARKER = "sync-status.sh --check"

_SHELL_CONTROL_OPERATORS = ("||", "&&", ";", "|")


def _job_block_lines(job_name: str) -> list[str]:
    """Isoliert die Rohtext-Zeilen eines Jobs aus ci.yml.

    Sucht die Zeile, deren `strip()` gleich `"<job_name>:"` ist, und sammelt
    alle Folgezeilen bis zur naechsten Job-Kopfzeile (zwei Leerzeichen
    Einrueckung, danach ein Nicht-Leerzeichen-Zeichen) oder bis zum
    Dateiende. Verlaesst sich bewusst nicht auf feste Zeilennummern, damit
    der Test stabil bleibt, wenn andere Jobs im Workflow verschoben oder
    ergaenzt werden.
    """
    lines = CI_WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    marker = f"{job_name}:"

    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == marker:
            start = index + 1
            break
    if start is None:
        raise AssertionError(f"Job {job_name!r} nicht in {CI_WORKFLOW_PATH} gefunden.")

    block: list[str] = []
    for line in lines[start:]:
        if line[:2] == "  " and len(line) > 2 and line[2] != " ":
            break  # naechste Job-Kopfzeile auf Top-Level-Einrueckung erreicht
        block.append(line)
    return block


def _parse_steps(block: list[str]) -> list[dict[str, str]]:
    """Parst die Steps-Liste eines Job-Blocks sequenziell aus Rohtext.

    Ein neuer Step beginnt an einer Zeile, deren `strip()` mit `"- "`
    beginnt. Pro Step werden `name:` und `run:` eingesammelt. Ein
    `run: |`/`run: >`-Block-Scalar wird defensiv unterstuetzt: Folgezeilen
    mit tieferer Einrueckung als die `run:`-Zeile selbst werden angehaengt
    (kommt aktuell in ci.yml nicht vor, soll aber nicht stillschweigend
    falsch geparst werden, falls sich das aendert).
    """
    steps: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    run_block_indent: int | None = None

    for line in block:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if stripped.startswith("- "):
            current = {}
            steps.append(current)
            run_block_indent = None
            remainder = stripped[2:]
            if remainder.startswith("name:"):
                current["name"] = remainder[len("name:") :].strip()
            continue

        if current is None:
            continue  # Zeilen vor dem ersten Step (sollte es hier nicht geben)

        if run_block_indent is not None:
            if indent > run_block_indent:
                current["run"] = current.get("run", "") + "\n" + stripped
                continue
            run_block_indent = None  # Block-Scalar zu Ende, Zeile normal auswerten

        if stripped.startswith("name:"):
            current["name"] = stripped[len("name:") :].strip()
        elif stripped.startswith("run:"):
            value = stripped[len("run:") :].strip()
            if value in ("|", ">"):
                run_block_indent = indent
                current["run"] = ""
            else:
                current["run"] = value

    return steps


def _backend_pr_gate_steps() -> list[dict[str, str]]:
    return _parse_steps(_job_block_lines(BACKEND_PR_GATE_JOB))


def _index_of_step_named(steps: list[dict[str, str]], name: str) -> int:
    for index, step in enumerate(steps):
        if step.get("name") == name:
            return index
    raise AssertionError(
        f"Step {name!r} nicht in Job {BACKEND_PR_GATE_JOB!r} gefunden."
    )


def _index_of_step_running(steps: list[dict[str, str]], substring: str) -> int:
    for index, step in enumerate(steps):
        if substring in step.get("run", ""):
            return index
    raise AssertionError(
        f"Kein Step mit '{substring}' im run-Kommando in Job "
        f"{BACKEND_PR_GATE_JOB!r} gefunden."
    )


def _ci_ruff_run_command() -> str:
    steps = _backend_pr_gate_steps()
    index = _index_of_step_named(steps, RUFF_STEP_NAME)
    return steps[index]["run"]


def _pre_push_gate_ruff_command() -> str:
    """Sucht die 'uv run ruff check'-Zeile innerhalb von run_backend() in
    pre-push-gate.sh. Sucht bewusst nach 'uv run ruff check' statt nur
    'ruff check', damit die vorangehende 'step "Backend: ruff check"'-
    Beschriftungszeile nicht faelschlich als Kommandozeile erkannt wird."""
    lines = PRE_PUSH_GATE_PATH.read_text(encoding="utf-8").splitlines()
    in_run_backend = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("run_backend()"):
            in_run_backend = True
            continue
        if in_run_backend and stripped == "}":
            break
        if in_run_backend and "uv run ruff check" in stripped:
            return stripped
    raise AssertionError(
        "Keine 'uv run ruff check'-Zeile in run_backend() von pre-push-gate.sh "
        "gefunden."
    )


def _extract_ruff_scope(run_command: str) -> set[str]:
    """Extrahiert die Menge der Ruff-Zielpfade aus einem 'ruff check ...'-Kommando.

    Alles nach dem Token 'ruff check' wird betrachtet, mit Ausnahme von Flags
    (Tokens, die mit '-' beginnen) und allem nach dem ersten Shell-Steuerzeichen
    (z. B. '|| fail ...'), damit Folgekommandos nicht in den Scope einfliessen.
    """
    marker = "ruff check"
    start = run_command.index(marker) + len(marker)
    remainder = run_command[start:]

    cutoffs = [
        remainder.index(op)
        for op in _SHELL_CONTROL_OPERATORS
        if op in remainder
    ]
    if cutoffs:
        remainder = remainder[: min(cutoffs)]

    scope: set[str] = set()
    for raw_token in remainder.split():
        # Loese Shell-Begleitzeichen wie schliessende Klammern oder
        # Anfuehrungszeichen von echten Pfad-Tokens, ohne den Pfad selbst
        # (z. B. das trailing '/') anzutasten.
        token = raw_token.strip("()\"';")
        if token and not token.startswith("-"):
            scope.add(token)
    return scope


def test_ci_pr_gate_and_pre_push_gate_ruff_scope_match() -> None:
    """Das verpflichtende PR-Gate und das lokale Pre-Push-Gate duerfen im
    Ruff-Scope nicht auseinanderlaufen (Issue #881)."""
    ci_command = _ci_ruff_run_command()
    pre_push_command = _pre_push_gate_ruff_command()

    ci_scope = _extract_ruff_scope(ci_command)
    pre_push_scope = _extract_ruff_scope(pre_push_command)

    assert ci_scope == pre_push_scope, (
        "Ruff-Scope zwischen CI-PR-Gate und lokalem Pre-Push-Gate laeuft "
        f"auseinander: ci.yml ({BACKEND_PR_GATE_JOB} / {RUFF_STEP_NAME!r}) "
        f"prueft {sorted(ci_scope)!r}, pre-push-gate.sh (run_backend) prueft "
        f"{sorted(pre_push_scope)!r}."
    )


def test_ci_pr_gate_ruff_scope_covers_tests_dir() -> None:
    """Ein Lint-Verstoss unter backend/tests/ muss das PR-Gate rot werden lassen
    (Akzeptanzkriterium 2 aus Issue #881)."""
    ci_scope = _extract_ruff_scope(_ci_ruff_run_command())

    # "." lintet das gesamte Backend-Verzeichnis und schliesst tests/ (und
    # scripts/, siehe Ruff-Scope-Luecke hinter dem main-Rotlauf vom 2026-08-08)
    # mit ein.
    assert "." in ci_scope or "tests/" in ci_scope or "tests" in ci_scope, (
        "Das CI-PR-Gate muss backend/tests/ linten, damit Lint-Verstoesse dort "
        f"das PR-Gate rot werden lassen. Gefundener Scope: {sorted(ci_scope)!r}."
    )


def test_ci_pr_gate_ruff_scope_covers_scripts_dir() -> None:
    """Ein Lint-Verstoss unter backend/scripts/ muss das PR-Gate rot werden
    lassen. Regression fuer den main-Rotlauf vom 2026-08-08: das PR-Gate
    lintete nur app/ tests/, waehrend der push-Job auf main '.' lintete —
    Tabs in scripts/_sim_common.py passierten das PR-Gate und brachen main.
    Eine Rueckkehr beider Gates zu 'app/ tests/' wuerde den Parity-Test
    weiterhin bestehen; erst diese Assertion macht die Suite dann rot."""
    ci_scope = _extract_ruff_scope(_ci_ruff_run_command())

    assert "." in ci_scope or "scripts/" in ci_scope or "scripts" in ci_scope, (
        "Das CI-PR-Gate muss backend/scripts/ linten, damit Lint-Verstoesse "
        "dort nicht erst der push-Job auf main findet. Gefundener Scope: "
        f"{sorted(ci_scope)!r}."
    )


def test_status_drift_check_step_runs_after_pytest_contracts_step() -> None:
    """Schutz des Ergebnisses aus PR #884: der STATUS.md-drift-check-Step muss
    nach dem Pytest-contracts-Step im Job backend-pr-gate stehen."""
    steps = _backend_pr_gate_steps()

    pytest_index = _index_of_step_named(steps, PYTEST_CONTRACTS_STEP_NAME)
    drift_index = _index_of_step_running(steps, SYNC_STATUS_MARKER)

    assert drift_index > pytest_index, (
        f"Der Step mit '{SYNC_STATUS_MARKER}' (Index {drift_index}) muss nach "
        f"dem Step {PYTEST_CONTRACTS_STEP_NAME!r} (Index {pytest_index}) stehen."
    )
