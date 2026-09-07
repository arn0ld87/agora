### Behoben

- Die Backend-Testsuite läuft in einem frischen Checkout ohne `.env` durch. `LLM_API_KEY` wird in `tests/conftest.py` per `setdefault` vorbelegt; zuvor hing die Suite an einer lokalen `.env` beziehungsweise am Job-Env der CI. Ein exportierter Key gewinnt weiterhin, damit Läufe gegen ein echtes Provider-Backend möglich bleiben.
