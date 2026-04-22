"""
Web tools (Tavily)

Two optional tools for the ReportAgent / chat agent:
- web_search: search the live web for up-to-date information
- fetch_url:  read a specific URL and return cleaned text

Gated by TAVILY_API_KEY in .env. When the key is absent (or ENABLE_WEB_TOOLS=false),
the service reports itself as disabled and the tools are simply not registered.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from ..utils.logger import get_logger

logger = get_logger('agora.web_tools')

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
DEFAULT_TIMEOUT = 25.0


def _is_public_url(url: str) -> tuple[bool, str]:
    """
    Defense-in-Depth-Check: bricht ab, sobald die URL auf private/Loopback/
    Link-Local/Metadata-Adressen zeigt. Tavily fetcht die URL zwar extern, aber
    wir wollen weder durch DNS-Tricks noch durch fehlerhafte Proxy-Konfig einen
    internen Service triggern.
    """
    try:
        p = urlparse(url)
    except Exception:
        return False, "unparsable URL"
    if p.scheme not in ("http", "https"):
        return False, f"unsupported scheme {p.scheme!r}"
    host = p.hostname
    if not host:
        return False, "missing host"

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return False, f"dns resolution failed: {exc}"

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip zone-id for IPv6
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"host resolves to non-public address {ip}"
        # AWS/GCP/Azure Metadata-Endpunkte — doppelt prüfen, auch wenn is_link_local
        # sie meist bereits erwischt.
        if str(ip) in ("169.254.169.254", "fd00:ec2::254"):
            return False, "metadata endpoint blocked"
    return True, ""


class WebToolsService:
    """Thin wrapper around the Tavily REST API."""

    def __init__(self, api_key: Optional[str] = None, enabled: Optional[bool] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "").strip() or None
        env_enabled = os.environ.get("ENABLE_WEB_TOOLS", "true").strip().lower() not in ("0", "false", "no", "off")
        self.enabled = bool(self.api_key) and (env_enabled if enabled is None else enabled)

    def is_available(self) -> bool:
        return self.enabled

    # ---------------------------------------------------------------- search

    def web_search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Live web search via Tavily.

        Returns:
            {
                "query": str,
                "answer": Optional[str],        # Tavily-generated short answer
                "results": [
                    {"title": str, "url": str, "content": str, "score": float},
                    ...
                ],
                "error": Optional[str]
            }
        """
        if not self.enabled:
            return {"query": query, "results": [], "error": "Web tools disabled (no TAVILY_API_KEY)"}

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max(1, min(int(max_results or 5), 10)),
            "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
            "include_answer": True,
        }
        if include_domains:
            payload["include_domains"] = list(include_domains)
        if exclude_domains:
            payload["exclude_domains"] = list(exclude_domains)

        try:
            r = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json() or {}
        except requests.HTTPError as exc:
            logger.warning(f"Tavily search HTTP error: {exc} — body={getattr(exc.response, 'text', '')[:200]}")
            return {"query": query, "results": [], "error": f"Tavily HTTP {getattr(exc.response, 'status_code', '?')}"}
        except Exception as exc:
            logger.warning(f"Tavily search failed: {exc}")
            return {"query": query, "results": [], "error": str(exc)}

        results = []
        for item in (data.get("results") or [])[:payload["max_results"]]:
            results.append({
                "title": (item.get("title") or "").strip(),
                "url": item.get("url") or "",
                "content": (item.get("content") or "").strip(),
                "score": float(item.get("score") or 0.0),
            })

        return {
            "query": query,
            "answer": (data.get("answer") or "").strip() or None,
            "results": results,
            "error": None,
        }

    # ---------------------------------------------------------------- extract

    def fetch_url(self, url: str) -> Dict[str, Any]:
        """
        Fetch a specific URL and return its main text content.

        Returns:
            {"url": str, "title": Optional[str], "content": str, "error": Optional[str]}
        """
        if not self.enabled:
            return {"url": url, "content": "", "error": "Web tools disabled (no TAVILY_API_KEY)"}

        if not url or not url.startswith(("http://", "https://")):
            return {"url": url, "content": "", "error": "Invalid URL"}

        ok, reason = _is_public_url(url)
        if not ok:
            logger.warning(f"fetch_url blocked ({reason}): {url}")
            return {"url": url, "content": "", "error": f"URL rejected: {reason}"}

        payload = {"api_key": self.api_key, "urls": [url]}
        try:
            r = requests.post(TAVILY_EXTRACT_URL, json=payload, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json() or {}
        except requests.HTTPError as exc:
            logger.warning(f"Tavily extract HTTP error: {exc}")
            return {"url": url, "content": "", "error": f"Tavily HTTP {getattr(exc.response, 'status_code', '?')}"}
        except Exception as exc:
            logger.warning(f"Tavily extract failed: {exc}")
            return {"url": url, "content": "", "error": str(exc)}

        results = data.get("results") or []
        if not results:
            return {"url": url, "content": "", "error": "No content extracted"}

        first = results[0]
        return {
            "url": first.get("url") or url,
            "title": (first.get("title") or "").strip() or None,
            "content": (first.get("raw_content") or first.get("content") or "").strip(),
            "error": None,
        }

    # ---------------------------------------------------------------- formatting

    @staticmethod
    def format_search_result(result: Dict[str, Any]) -> str:
        """Format a search result dict as compact text for the agent context."""
        if result.get("error"):
            return f"[web_search error] {result['error']}"

        lines: List[str] = []
        if result.get("answer"):
            lines.append(f"Zusammenfassung: {result['answer']}")
            lines.append("")

        for i, r in enumerate(result.get("results", []), 1):
            lines.append(f"[{i}] {r['title']}")
            lines.append(f"    {r['url']}")
            snippet = r["content"][:500]
            if len(r["content"]) > 500:
                snippet += "…"
            lines.append(f"    {snippet}")
            lines.append("")
        return "\n".join(lines).strip() or "(keine Treffer)"

    @staticmethod
    def format_extract_result(result: Dict[str, Any], max_chars: int = 4000) -> str:
        if result.get("error"):
            return f"[fetch_url error] {result['error']}"
        head = f"URL: {result['url']}"
        if result.get("title"):
            head += f"\nTitel: {result['title']}"
        content = result.get("content", "")
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n…(abgeschnitten)"
        return f"{head}\n\n{content}".strip()
