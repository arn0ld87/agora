"""Trusted reverse-proxy helpers."""

from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


def apply_proxy_fix(app: Flask) -> bool:
    """Apply Werkzeug ProxyFix when explicitly configured.

    X-Forwarded-* headers are client-controlled unless a trusted reverse proxy
    strips and rewrites them. Keep this opt-in and configure the exact proxy
    count for the deployment topology.
    """

    counts = {
        "x_for": app.config["AGORA_PROXY_FIX_X_FOR"],
        "x_proto": app.config["AGORA_PROXY_FIX_X_PROTO"],
        "x_host": app.config["AGORA_PROXY_FIX_X_HOST"],
        "x_port": app.config["AGORA_PROXY_FIX_X_PORT"],
        "x_prefix": app.config["AGORA_PROXY_FIX_X_PREFIX"],
    }
    if not any(counts.values()):
        return False

    app.wsgi_app = ProxyFix(app.wsgi_app, **counts)
    return True
