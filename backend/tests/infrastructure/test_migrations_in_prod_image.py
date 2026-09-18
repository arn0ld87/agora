"""Die Alembic-Migrationen müssen im prod-Image liegen.

Befund aus dem Review von PR 2: die `prod`-Stage im Dockerfile kopiert
selektiv (`backend/app`, `backend/scripts`, …) statt `COPY . .` wie die
`dev`-Stage. `backend/migrations` fehlte dort — im Produktionscontainer wäre
`alembic upgrade head` schlicht nicht ausführbar gewesen, und das wäre erst
aufgefallen, wenn ein Zielsystem die erste Migration braucht.

Der Test hält die COPY-Zeile fest, nicht das Image: ein Docker-Build kostet
Minuten, das Lesen einer Zeile nichts. Das genügt für genau diesen Fehler —
eine selektive Kopierliste, aus der jemand ein Verzeichnis vergisst.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = REPO_ROOT / 'Dockerfile'
MIGRATIONS_DIR = REPO_ROOT / 'backend' / 'migrations'


def _prod_stage_lines() -> list[str]:
    """Die Zeilen der `prod`-Stage, bis zur nächsten `FROM`-Anweisung."""
    lines = DOCKERFILE.read_text(encoding='utf-8').splitlines()
    stage_start = re.compile(r'^\s*FROM\s', re.IGNORECASE)
    prod_start = re.compile(r'^\s*FROM\s+.*\bAS\s+prod\s*$', re.IGNORECASE)

    collected: list[str] = []
    inside = False
    for line in lines:
        if prod_start.match(line):
            inside = True
            continue
        if inside and stage_start.match(line):
            break
        if inside:
            collected.append(line)
    return collected


def test_dockerfile_has_a_prod_stage():
    """Ohne die Stage prüft der Test unten stillschweigend nichts."""
    assert _prod_stage_lines(), 'keine `AS prod`-Stage im Dockerfile gefunden'


def test_prod_stage_copies_backend_migrations():
    copied = [
        line
        for line in _prod_stage_lines()
        if line.lstrip().upper().startswith('COPY') and 'backend/migrations' in line
    ]

    assert copied, (
        'Die prod-Stage kopiert `backend/migrations` nicht. Sie kopiert '
        'selektiv, also muss das Verzeichnis dort ausdrücklich stehen — sonst '
        'ist `alembic upgrade head` im Produktionscontainer nicht ausführbar.'
    )


@pytest.mark.parametrize(
    'required',
    ['alembic.ini', 'env.py', 'script.py.mako', 'versions'],
)
def test_migrations_directory_is_complete(required):
    """Was kopiert wird, muss auch da sein.

    `env.py` und `script.py.mako` fehlen schnell: Alembic legt sie beim
    `init` an, und wer das Verzeichnis von Hand baut, vergisst das Template.
    """
    assert (MIGRATIONS_DIR / required).exists(), (
        f'backend/migrations/{required} fehlt'
    )


def test_alembic_ini_carries_no_database_url():
    """Eine Verbindungszeichenkette mit Passwort gehört nicht ins Repository.

    `env.py` liest `DATABASE_URL` aus der Umgebung. Ein `sqlalchemy.url` in
    der versionierten Datei wäre genau der Rückfall, den das vermeidet.
    """
    content = (MIGRATIONS_DIR / 'alembic.ini').read_text(encoding='utf-8')

    active = [
        line
        for line in content.splitlines()
        if line.strip().startswith('sqlalchemy.url')
    ]

    assert active == [], f'alembic.ini setzt sqlalchemy.url: {active}'
