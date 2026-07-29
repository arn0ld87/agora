"""
Pricing Registry (Issue #764).

Zentrale, versionierte Verwaltung von Provider-Richtpreisen. Einzige
Preisquelle im System — keine duplizierte Preislogik in anderen Modulen
oder im Frontend.

Datenquelle: ``backend/app/data/model_pricing.json`` mit ``pricing_version``
und ``pricing_source``. Preise sind Integer-Micros pro 1 Mio. Tokens
(1 USD = 1_000_000 Micros) und werden stets als Schätzung gekennzeichnet.

Kostenklassen:
  - priced:  statischer Richtpreis bekannt
  - free:    lokales Modell ohne Geldpreis (transport=local / Loopback-URL)
  - unknown: kein Preis bekannt — wird niemals als 0 ausgegeben
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

PricingStatus = Literal["priced", "free", "unknown"]

_DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "model_pricing.json"

# Provider-IDs/Vokabular, das als lokal gilt, wenn die URL ein Loopback ist.
_LOCAL_PROVIDER_HINTS = ("ollama", "local", "llamafile", "lmstudio")
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal", "0.0.0.0")


@dataclass(frozen=True)
class PricingQuote:
    """Aufgelöster Preis für (provider, model)."""

    status: PricingStatus
    input_per_mtok_micros: Optional[int] = None
    output_per_mtok_micros: Optional[int] = None
    pricing_version: str = "unknown"
    pricing_source: str = "unknown"

    def cost_micros(self, input_tokens: int, output_tokens: int) -> Optional[int]:
        """Kosten in Micros; None wenn unbekannt oder kostenfrei-ohne-Preis."""
        if self.status == "free":
            return 0
        if self.status != "priced":
            return None
        assert self.input_per_mtok_micros is not None
        assert self.output_per_mtok_micros is not None
        return (
            input_tokens * self.input_per_mtok_micros
            + output_tokens * self.output_per_mtok_micros
        ) // 1_000_000


def _is_loopback_url(base_url_sanitized: Optional[str]) -> bool:
    if not base_url_sanitized:
        return False
    lowered = base_url_sanitized.lower()
    return any(f"://{host}" in lowered for host in _LOOPBACK_HOSTS)


class PricingRegistry:
    """Lädt und beantwortet Preisanfragen gegen die versionierte Preistabelle."""

    def __init__(self, data_path: Optional[Path] = None):
        self._data_path = data_path or _DEFAULT_DATA_PATH
        self._raw = self._load(self._data_path)
        self.pricing_version: str = str(self._raw.get("pricing_version", "unknown"))
        self.pricing_source: str = str(self._raw.get("pricing_source", str(self._data_path)))
        # Einträge je Provider: längster Prefix zuerst (gpt-4o-mini vor gpt-4o).
        self._entries: dict[str, list[tuple[str, int, int]]] = {}
        for provider, items in (self._raw.get("providers") or {}).items():
            rows = [
                (str(item["match"]).lower(), int(item["input"]), int(item["output"]))
                for item in items
            ]
            rows.sort(key=lambda row: len(row[0]), reverse=True)
            self._entries[provider.lower()] = rows

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            # Issue #764 (Codex P1): korrupte model_pricing.json darf nicht
            # zum Crash von get_pricing_registry fuehren — wir fallen auf
            # ein leeres Dict zurueck, damit zumindest free-Modelle noch
            # ehrlich bepreist werden und der Rest als unknown markiert ist.
            return {}

    def resolve(
        self,
        provider_id: Optional[str],
        model: Optional[str],
        base_url_sanitized: Optional[str] = None,
    ) -> PricingQuote:
        """Preis für (provider, model) auflösen.

        Lokale Modelle (Loopback-URL oder lokaler Provider-Hinweis mit
        Loopback) sind „free". Unbekannte Preise sind „unknown".
        """
        provider = (provider_id or "").lower()
        model_name = (model or "").lower()

        if _is_loopback_url(base_url_sanitized) and any(
            hint in provider for hint in _LOCAL_PROVIDER_HINTS
        ):
            return PricingQuote(
                status="free",
                pricing_version=self.pricing_version,
                pricing_source=self.pricing_source,
            )
        if _is_loopback_url(base_url_sanitized) and not provider:
            return PricingQuote(
                status="free",
                pricing_version=self.pricing_version,
                pricing_source=self.pricing_source,
            )

        for provider_key, rows in self._entries.items():
            if provider_key not in provider:
                continue
            for match, input_micros, output_micros in rows:
                if model_name.startswith(match):
                    return PricingQuote(
                        status="priced",
                        input_per_mtok_micros=input_micros,
                        output_per_mtok_micros=output_micros,
                        pricing_version=self.pricing_version,
                        pricing_source=self.pricing_source,
                    )
        return PricingQuote(
            status="unknown",
            pricing_version=self.pricing_version,
            pricing_source=self.pricing_source,
        )


_instance: Optional[PricingRegistry] = None
_lock = threading.Lock()


def get_pricing_registry() -> PricingRegistry:
    """Prozessweites Singleton (Preisdaten ändern sich nicht zur Laufzeit)."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = PricingRegistry()
    return _instance


def reset_pricing_registry() -> None:
    """Test-Hook: Singleton zurücksetzen (z. B. für alternative Preisdateien)."""
    global _instance
    with _lock:
        _instance = None
