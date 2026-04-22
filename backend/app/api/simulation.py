"""
Compatibility shim for simulation-related API routes.

The original monolithic simulation API module has been split into focused modules:
- simulation_common.py
- simulation_lifecycle.py
- simulation_entities.py
- simulation_prepare.py
- simulation_profiles.py
- simulation_run.py
- simulation_interviews.py
- simulation_history.py

This file remains so existing imports from `app.api.simulation` do not break during
an incremental refactor. Route registration now happens in the split modules via
`app/api/__init__.py`.
"""
