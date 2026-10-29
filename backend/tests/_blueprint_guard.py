"""Geerbte Auth-Guards aus Test-Apps entfernen.

``create_app()`` installiert per ``install_blueprint_guard`` einen
``before_request``-Hook an den modulweiten Blueprint-Singletons
(``simulation_bp``, ``runs_bp``, ``user_profile_bp`` ...). Jede spätere App,
die dasselbe Blueprint registriert, erbt ihn — auch eine schlanke Test-App, die
den Principal selbst per ``set_principal`` setzt. Weil Blueprint-Hooks nach den
App-Hooks laufen, ersetzt der Guard im offenen Modus den Test-Principal durch
einen anonymen. Tests, die im selben xdist-Worker nach einem ``create_app()``
laufen, prüfen dann einen anderen Principal als gemeint.

Entfernt wird ausschließlich der Guard; eigene Hooks des Blueprints (etwa das
Rate-Limit in ``simulation_common``) bleiben erhalten.
"""

from __future__ import annotations

from flask import Flask

_GUARD_QUALNAME_PREFIX = "install_blueprint_guard."


def drop_inherited_auth_guards(app: Flask) -> None:
    """Entfernt die von ``install_blueprint_guard`` geerbten Hooks aus ``app``."""
    for key, funcs in list(app.before_request_funcs.items()):
        app.before_request_funcs[key] = [
            fn
            for fn in funcs
            if not getattr(fn, "__qualname__", "").startswith(_GUARD_QUALNAME_PREFIX)
        ]
