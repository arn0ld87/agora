# Runbook: Simulations-Recommender (Twitter vs. Reddit)

**Zweck:** Erklärt, warum der Twitter-Feed pro Runde ein BERT-Modell lädt und
der Reddit-Feed nicht, wie der TWHIN-BERT-Cache offline gehalten wird, und
was der Transformers-Ladereport beim Start tatsächlich bedeutet.

Umgesetzt in Issue #1713, Slice S3 — Zuverlässigkeit.

---

## Warum Twitter BERT braucht und Reddit nicht

OASIS betreibt zwei strukturell unterschiedliche Recommender:

- **Twitter — `rec_sys_personalized_twh`** (`oasis/social_platform/recsys.py`,
  Zeilen 419-606): personalisiert. Baut pro Agent ein Profil-Embedding aus
  Bio + letztem Post, embedded jeden Kandidaten-Post mit
  `Twitter/twhin-bert-base`, rankt über Cosinus-Ähnlichkeit × Recency-Faktor.
  Zusätzlich fließen die Posts der eigenen Followees in einen Refresh-Schritt
  ein (`platform.py:285-304`). Defaults (`env.py:78-85`):
  `refresh_rec_post_count=2`, `max_rec_post_len=2`, `following_post_count=3`.
- **Reddit — `rec_sys_reddit`** (`oasis/social_platform/recsys.py`,
  Zeilen 168-257): nicht personalisiert. Hot-Score aus `likes − dislikes` und
  Alter, **identische Liste für alle Agenten** — kein BERT, keine
  Persona-Individualisierung im Feed selbst.

**Relevanz für die Auswertung:** Ein Unterschied zwischen simulierten
Twitter- und Reddit-Reaktionen kann ein Artefakt des Recommenders sein (echte
Personalisierung vs. globaler Hot-Feed), nicht zwingend ein Unterschied in
der Persona-Reaktion selbst. Die Asymmetrie ist historisch gewachsen
(OASIS-Upstream-Design) — ein möglicher späterer Punkt, keine für dieses
Issue geplante Architekturänderung.

`install_recsys_mean_pooling_patch` (`backend/scripts/_sim_common.py`)
patcht `process_recsys_posts.process_batch` unabhängig davon, ob eine
Simulation Twitter oder Reddit fährt — auf Reddit bleibt der Patch folgenlos,
weil `rec_sys_reddit` ihn nie aufruft (#1236, siehe Docstring im Code).

## Cache-Verhalten und Offline-Modus (#1713 S3)

`Twitter/twhin-bert-base` (~1,1 GB) lädt OASIS über
`AutoModel`/`AutoTokenizer.from_pretrained` ohne `cache_dir` oder
`local_files_only`. Ohne weitere Vorkehrung spricht das bei **jedem**
Prozessstart den Hugging-Face-Hub für eine Revisions-/Vollständigkeitsprüfung
an — auch wenn der Checkpoint längst lokal vorliegt.

- **Persistenter Cache:** Bind-Mount `./backend/.cache/huggingface` →
  `/home/agora/.cache/huggingface` (`docker-compose.yml`), liegt außerhalb
  des 256-MB-`tmpfs` unter `/home/agora/.cache`. `HF_HOME` zeigt seit diesem
  Slice explizit dorthin — unabhängig vom (im OASIS-Subprozess teils
  isolierten) `$HOME`.
- **Warmup + Offline:** `ensure_twhin_cache()`
  (`backend/scripts/_sim_common.py`, aufgerufen aus
  `install_bert_memory_profile`, das alle drei Runner-Skripte ohnehin vor dem
  `oasis`-Import ausführen) prüft den Cache über
  `huggingface_hub.snapshot_download(..., local_files_only=True)`. Ist er
  vollständig, wird sofort `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`
  gesetzt — kein Netzwerkzugriff mehr für den Rest des Prozesses. Fehlt
  etwas, lädt genau ein Online-Download (`local_files_only=False`) den
  Checkpoint einmalig nach, danach ebenfalls offline. Scheitert auch dieser
  Download, bricht der Lauf mit `TwhinCacheError` sichtbar ab — kein
  stiller Fallback auf ein halb geladenes Modell.
- **Reddit-Only-Läufe** (`run_reddit_simulation.py`) rufen
  `install_bert_memory_profile(needs_twhin_bert=False)` auf: kein
  Cache-Warmup/-Download für ein Modell, das `rec_sys_reddit` nie lädt.
  `run_twitter_simulation.py` und `run_parallel_simulation.py` behalten den
  Default (`needs_twhin_bert=True`).

## Ladereport-Zeilen richtig lesen

Beim Laden meldet Transformers zwei WARNING-Blöcke für
`Twitter/twhin-bert-base` — beide sind **erwartet**, seit der
Mean-Pooling-Fix (#1236) den Recommender von `pooler_output` auf
`last_hidden_state` umgestellt hat:

- `pooler.dense.{weight,bias}` **MISSING** (neu initialisiert): der
  Checkpoint ist ein Masked-LM-Checkpoint ohne trainierten Pooler. Da der
  Recommender den Pooler seit #1236 nicht mehr liest, ist das folgenlos.
- `cls.predictions.*` **UNEXPECTED** (im Checkpoint vorhanden, aber
  verworfen): der MLM-Kopf wird nicht gebraucht, nur der Encoder liefert die
  Embeddings.

`TwhinBertLoadReportFilter` (`backend/scripts/_sim_common.py`, installiert
über `install_twhin_bert_load_report_filter`, Teil von
`install_bert_memory_profile`) erkennt genau diese beiden Fälle und
protokolliert sie als erklärende INFO-Zeile statt als WARNING. **Andere**
MISSING-Gewichte (z. B. bei einem künftigen Checkpoint-Wechsel) oder ein
anderer Modellname bleiben unverändert als WARNING sichtbar — der Filter
dämpft nur die zwei bekannten, harmlosen Fälle.

## Relevante Env-Variablen

| Variable | Default | Zweck |
|---|---|---|
| `HF_HOME` | `/home/agora/.cache/huggingface` (Compose) | Cache-Root für `huggingface_hub`/`transformers` |
| `HF_TOKEN` | leer | Authentifizierte Hub-Downloads (Rate-Limit-Schutz beim Warmup) |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | wird von `ensure_twhin_cache` zur Laufzeit gesetzt | Kein Netzwerkzugriff nach erfolgreichem Warmup |
| `AGORA_BERT_MEMORY_PROFILE` | `auto` | fp16/fp32-Ladeprofil (siehe Modul-Docstring in `_sim_common.py`) |
