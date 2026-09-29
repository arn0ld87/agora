### Fixed

- Der Twitter-Recommender lud `Twitter/twhin-bert-base` bei jedem OASIS-Prozessstart mit
  einer Hugging-Face-Hub-Anfrage, selbst wenn der ~1,1-GB-Checkpoint bereits vollständig im
  persistenten Cache (`./backend/.cache/huggingface`) lag — ein unnötiger Netzwerk-Soft-Point
  vor der ersten Twitter-Runde. `ensure_twhin_cache()` prüft den Cache jetzt einmal vor dem
  `oasis`-Import und schaltet den Prozess bei vollständigem Cache sofort in den
  `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`-Modus; fehlt etwas, lädt genau ein Warmup-Download
  nach, danach ebenfalls offline. Scheitert der Download, bricht der Lauf sichtbar mit
  `TwhinCacheError` ab statt mit einem halb geladenen Modell weiterzulaufen.
  `docker-compose.yml`/`docker-compose.prod.yml` setzen dafür `HF_HOME` explizit.
  Reine Reddit-Läufe (`run_reddit_simulation.py`) lösen keinen Cache-Warmup mehr aus, weil
  `rec_sys_reddit` kein BERT nutzt.
- Der erwartete Transformers-Ladereport für `Twitter/twhin-bert-base`
  (`pooler.dense.*` MISSING, `cls.predictions.*` UNEXPECTED — beide Folge des
  Mean-Pooling-Fixes #1236) erschien als WARNING, obwohl beides für diesen Checkpoint
  harmlos ist. Ein Logging-Filter übersetzt genau diese beiden bekannten Fälle in eine
  erklärende INFO-Zeile; andere oder zusätzliche fehlende Gewichte bleiben als WARNING
  sichtbar.
