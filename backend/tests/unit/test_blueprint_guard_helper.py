"""Regression: geerbte Auth-Guards verfälschten Test-Principals unter xdist."""

from __future__ import annotations

from flask import Blueprint, Flask

from app.utils.auth import install_blueprint_guard
from tests._blueprint_guard import drop_inherited_auth_guards


def _own_hook() -> None:
    return None


def test_drops_only_the_inherited_guard() -> None:
    bp = Blueprint("guard_helper_probe", __name__)
    bp.before_request(_own_hook)
    install_blueprint_guard(bp)
    app = Flask(__name__)
    app.register_blueprint(bp)
    assert any(
        fn.__qualname__.startswith("install_blueprint_guard.")
        for fn in app.before_request_funcs[bp.name]
    )

    drop_inherited_auth_guards(app)

    assert app.before_request_funcs[bp.name] == [_own_hook]
