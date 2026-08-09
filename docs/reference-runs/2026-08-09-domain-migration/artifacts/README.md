# Artefakte des Referenzlaufs

Diese Dateien dokumentieren die Provenienz des historischen Laufs `report_41f7b1bcf1e4` / `sim_1d96603073ae`.

## Öffentlich versionierter Extract

[`evidence-extract.json`](./evidence-extract.json) ist ein deterministisch erzeugter, öffentlicher Auszug aus dem vollständigen Evidence-Export. Er enthält ausschließlich die Felder, die in der Case Study direkt ausgewertet werden:

- Simulation-Metrics-Snapshot,
- ausgewählte Social-Actions,
- `RELATED_ONLY`-Beispiele,
- `INSUFFICIENT`-Beispiele,
- Reviewer-Floor-Beispiele,
- vollständigen `degradation_log` des Exports.

Der Extract ersetzt den vollständigen historischen Export **nicht**. Insbesondere ist er kein neues Agora-Reportformat.

## Prüfsummen der für diese Evaluation verwendeten Originalexporte

| Originalartefakt | Größe | SHA-256 |
|---|---:|---|
| `agora-report-report_41f7b1bcf1e4-evidence.json` | 419.716 B | `a596c8866379dbb86f965850bb7a98ee1b004e2b2b565809fa3c26314caafccf` |
| `agora-report-report_41f7b1bcf1e4.md` | 98.716 B | `3d8ef1522b91228c4fe0f23874ded91f504bd8fd4a0f7f8ef6d4994f96ba89d9` |
| `agora-report-report_41f7b1bcf1e4.html` | nicht als kanonische Quelle verwendet | `1a9e2b098f651cc01956d7c2611b3b7118fd51cc04a8cc2e632255e1de9e178b` |
| `Agora-Report · report_41f7b1bcf1e4.pdf` | 60 Seiten | `2960d57fcab7a22eb93ba84276e0fc43087805d39d2daeb918530198bd7878f1` |

Die Markdown- und Evidence-Exporte waren die primären Quellen für die öffentliche Auswertung. PDF und HTML sind Darstellungsvarianten desselben Reports.

## Warum nicht alle generierten Exporte im Git-Tree liegen

Die Case Study soll reviewbar bleiben und keinen zweiten, mehrere hundert Kilobyte großen generierten Reportbestand als vermeintliche Dokumentations-SSoT etablieren. Deshalb wird im Git-Tree ein kleiner deterministischer Evidence-Extract plus kryptografische Prüfsummen versioniert. Vollständige historische Export-Bundles können später an einen Release- oder Zenodo-Snapshot gehängt werden, ohne die Case Study rückwirkend umzuschreiben.
