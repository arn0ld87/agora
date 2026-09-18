Projektmetadaten haben einen Pydantic-Vertrag (`app/contracts/project_contract.py`)
und eine Repository-Grenze (`ProjectRepository` mit dem Dateiadapter
`FileProjectRepository`). `Project` war bisher eine Dataclass, deren `to_dict()`
über drei Endpunkte ausgeliefert wurde — eine Dataclass auf einer API-Grenze.

An der Ablage ändert sich nichts: `uploads/projects/<project_id>/project.json`
behält Pfad, Schlüssel und Reihenfolge, `ProjectManager` bleibt als Fassade
stehen, und `AGORA_PROJECT_BACKEND` steht im Default auf `file`. Artefakte
(`files/`, `extracted_text.txt`, Dokument-Manifest) bleiben ausdrücklich außerhalb
des Ports.
