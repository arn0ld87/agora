"""Architecture regression tests for the simulation-prepare split.

The API module keeps its historical compatibility surface while the heavy
implementation is split into focused Python modules.
"""


def test_simulation_prepare_split_modules_exist_and_reexport_contracts():
    from app.api import simulation_prepare as facade
    from app.api import simulation_prepare_contracts as contracts
    from app.api import simulation_prepare_jobs as jobs
    from app.api import simulation_prepare_state as state

    assert facade._PrepareRejected is contracts.PrepareRejected
    assert facade._PrepareRequest is contracts.PrepareRequest
    assert facade._PrepareRouting is contracts.PrepareRouting
    assert facade._PrepareInputs is contracts.PrepareInputs
    assert facade._ClientChoice is contracts.ClientChoice

    assert callable(jobs.make_prepare_job)
    assert callable(jobs.build_progress_callback)
    assert callable(state.check_simulation_prepared)
