"""
Invarianten des Default-Compose-Stacks.

Diese Tests parsen die Compose-Dateien direkt statt ueber `docker compose
config`: die Aussagen hier gelten unabhaengig davon, ob auf dem Testhost eine
Docker-Engine laeuft, und sollen genau dann rot werden, wenn jemand einen
entfernten Default wieder einfuehrt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE = REPO_ROOT / "docker-compose.yml"
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
EXTERNAL_DNS_OVERRIDE = REPO_ROOT / "deploy" / "compose" / "docker-compose.external-dns.yml"


class _ComposeLoader(yaml.SafeLoader):
    """SafeLoader, der Compose-eigene Tags wie `!override`/`!reset` toleriert.

    Diese Tags steuern das Merge-Verhalten zwischen Compose-Dateien und sind
    fuer die Invarianten hier ohne Bedeutung — uns interessiert nur der Wert.
    """


def _ignore_unknown_tag(loader: yaml.Loader, tag_suffix: str, node: yaml.Node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _ignore_unknown_tag)


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}


# --------------------------------------------------------------------------- #
# DNS
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("compose_file", [DEV_COMPOSE, PROD_COMPOSE])
def test_no_dns_default_in_shipped_stack(compose_file: Path):
    """Der Standard-Stack erbt den Resolver der Engine.

    Ein hart gesetzter oeffentlicher Resolver bricht Split-DNS (Tailscale
    MagicDNS, Homelab-Zonen) und schickt ausserdem jede Namensaufloesung an
    einen Dritten — beides widerspricht dem local-first-Default.
    """
    config = _load(compose_file)
    for name, service in (config.get("services") or {}).items():
        assert "dns" not in (service or {}), (
            f"{compose_file.name}::{name} setzt wieder einen DNS-Default; "
            f"externe Resolver gehoeren in {EXTERNAL_DNS_OVERRIDE.name}"
        )


@pytest.mark.parametrize("compose_file", [DEV_COMPOSE, PROD_COMPOSE])
def test_no_hardcoded_public_resolver(compose_file: Path):
    raw = compose_file.read_text(encoding="utf-8")
    for resolver in ("8.8.8.8", "8.8.4.4", "1.1.1.1"):
        assert resolver not in raw, (
            f"{compose_file.name} enthaelt den oeffentlichen Resolver {resolver}"
        )


def test_external_dns_override_exists_and_requires_both_values():
    """Das Override darf nicht still auf einen Default zurueckfallen.

    Compose-Syntax `${VAR:?msg}` bricht mit Fehlermeldung ab, wenn VAR fehlt —
    im Gegensatz zu `${VAR:-default}`, das genau den Zustand wiederherstellen
    wuerde, den dieser Fix entfernt hat.
    """
    assert EXTERNAL_DNS_OVERRIDE.is_file(), f"{EXTERNAL_DNS_OVERRIDE} fehlt"
    raw = EXTERNAL_DNS_OVERRIDE.read_text(encoding="utf-8")

    dns_entries = _load(EXTERNAL_DNS_OVERRIDE)["services"]["agora"]["dns"]
    assert len(dns_entries) == 2

    for var in ("AGORA_DNS_PRIMARY", "AGORA_DNS_SECONDARY"):
        assert f"${{{var}:?" in raw, (
            f"{var} muss im Override als Pflichtvariable (`${{{var}:?...}}`) "
            "deklariert sein"
        )
        assert f"${{{var}:-" not in raw, (
            f"{var} hat im Override einen stillen Default — genau das war der Bug"
        )
