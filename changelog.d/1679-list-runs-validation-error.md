### Fixed

- `GET /api/runs` gab bei ungültigen Filterparametern die rohe Pydantic-`errors()`-Liste im `error`-Feld zurück; ein Validator mit `ValueError` im `ctx` hätte daraus eine 500 gemacht. Die Antwort ist jetzt ein regulärer 400-Envelope mit `code: "validation_error"`, Text in `error` und sanitisierten Details unter `details` — wie im Replay-Pfad (#1273). (#1679)
