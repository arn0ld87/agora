# ADR-0015: Der Webprozess bleibt bei einem Worker

- Status: akzeptiert
- Datum: 2026-09-19
- Bezug: [`backend/gunicorn.conf.py`](../../backend/gunicorn.conf.py) Zeilen 38–48,
  Code-Review 2026-05-17 Finding 1.2
- Hängt zusammen mit [#1472](https://github.com/arn0ld87/agora/issues/1472)
  (Release-Priorität 1, restart-sichere Langläufer)

## Kontext

`workers = 1` steht seit dem Code-Review vom 2026-05-17 als HARDSTOP in der
gunicorn-Konfiguration, begründet durch einen Kommentar von zehn Zeilen, der
fünf Komponenten nennt. Was das Anheben tatsächlich kostet, stand nirgends.
Damit war die Frage bei jeder Betriebsdiskussion neu offen.

Dieser ADR beziffert sie. Er ändert **keinen** Produktionscode.

## Befund

Der Kommentar in der Konfiguration ist unvollständig, und seine Aufzählung führt
in die Irre, weil sie ungleiche Dinge nebeneinanderstellt. Der eigentliche
Ertrag der Untersuchung ist eine Einteilung in **drei** Klassen, die den Aufwand
bestimmt — und die dritte entscheidet die Sache.

### Klasse A: reiner Prozesszustand ohne geteilten Ort

Datenwerte, die nur im Speicher existieren. Sie ließen sich verschieben; es gibt
nur noch keinen Ort dafür.

| Was | Wo |
|---|---|
| `_monitor_generations: Dict[str, int]` | [`simulation_runner.py:112`](../../backend/app/services/simulation_runner.py) |
| `_cancel_flags: Dict[str, threading.Event]` | [`sim/cancel_flag.py:28`](../../backend/app/services/sim/cancel_flag.py) |
| `_start_locks: Dict[str, threading.Lock]` | [`sim/process_manager.py:101`](../../backend/app/services/sim/process_manager.py) |

Der Generationszähler ist die Wache gegen einen veralteten Monitor nach einem
erzwungenen Neustart; sie wird als `is_current_generation` in den Monitor
injiziert (`simulation_runner.py:407`) und wirkt nur innerhalb eines Prozesses.

`cancel_flag.py` benennt sein eigenes Problem im Modul-Docstring: „Kein Redis,
kein File-IO — rein in-process. Falls künftig multi-worker gebraucht wird,
dieses Modul gegen einen Redis-Adapter austauschen." Ein Abbruchwunsch, der im
falschen Worker ankommt, wird nie gesehen.

`_start_locks` serialisiert den Start je `simulation_id`. Mit zwei Workern gibt
es keinen gemeinsamen Lock mehr und damit keine Garantie gegen den doppelten
Start derselben Simulation.

### Klasse B: geteilter Ort existiert, der Cache oder die fehlende Sperre davor ist das Problem

**`RunRegistry`** — [`run_registry.py:43,53`](../../backend/app/services/run_registry.py).
`_cache` ist ein reiner Write-Through-Cache; jede Änderung geht sofort nach
`uploads/run_registry/<run_id>.json`. `write_json_atomic`
([`utils/json_io.py`](../../backend/app/utils/json_io.py)) ist über `mkstemp`,
`fsync` und `os.replace` echt atomar — aber `update_run` hält für den Zyklus aus
Lesen, Ändern und Schreiben nur ein `threading.Lock`, und das ist prozesslokal.

Das ist billiger, als es klingt: **das Muster ist im Repo bereits gelöst.**
[`services/json_file_store.py:28-56`](../../backend/app/services/json_file_store.py)
hält einen `fcntl.flock` über den gesamten Zyklus, mit genau dieser Begründung,
und wird von `OnboardingStateStore`, `UserProfileStore` und
`WorkspaceRoutingStore` benutzt. Für `RunRegistry` wäre es eine Übernahme, keine
Neuentwicklung.

**`ApiKeysStore`** — [`api_keys_store.py:104,254`](../../backend/app/services/api_keys_store.py).
Modul-Singleton über `api_keys_persistence` (`data/api_keys.json`), dazu ein
Schreibsparer: `last_used_at` wird höchstens alle 60 Sekunden persistiert.

Entscheidend, und schwerer als zunächst angenommen: `_load_from_disk()` wird
**ausschließlich im Konstruktor** aufgerufen (`:104`). Es gibt kein periodisches
Nachladen. Ein in einem Worker widerrufener Schlüssel bliebe im anderen bis zu
dessen **Neustart** gültig — nicht bis zu einem nächsten Nachladen, das es gar
nicht gibt.

**`TaskManager`** — [`models/task.py:110-111,174-182`](../../backend/app/models/task.py).
Der Singleton hält `_tasks` im Speicher, schreibt aber über
`RunRegistry().sync_task(task)` bei jedem `create_task` und `update_task`
durch, und `get_task` fällt bei einem Cache-Fehlschlag auf die Rekonstruktion
aus dem Lauf-Manifest zurück. Ein zweiter Worker scheitert also **nicht**, er
liefert Degradiertes: die Rekonstruktion trägt kein `progress_detail` (`:44`).

### Klasse C: nicht verschiebbar

Das ist der Teil, der die Entscheidung trägt, und im Konfigurationskommentar
fehlt er ganz. [`simulation_runner.py:102-116`](../../backend/app/services/simulation_runner.py)
hält acht klassenweite Dicts, darunter:

| Was | Typ |
|---|---|
| `_processes` | `Dict[str, subprocess.Popen]` |
| `_action_queues` | `Dict[str, Queue]` |
| `_stdout_files`, `_stderr_files` | offene Dateiobjekte |

Das sind keine Datenwerte, sondern **lebende Betriebssystem-Handles**: ein
Subprozess-Objekt, eine In-Prozess-Queue, offene Dateideskriptoren. Sie lassen
sich nicht serialisieren und nicht in Redis legen. Ein zweiter Worker, der eine
Pause- oder Stop-Aktion für einen Lauf verarbeitet, den der erste gestartet hat,
hätte selbst mit einem geteilten Generationszähler keinen Zugriff auf dessen
Queue (`sim/process_manager.py:448` legt sie rein im Speicher ab).

**Klasse C ist durch keine geteilte Ablage zu lösen.** Sie ist nur dadurch zu
lösen, dass genau ein Prozess einen gegebenen Lauf besitzt.

### Was Redis hier beiträgt — weniger, als es scheint

Redis ist vorhanden, aber **überall optional und mit Rückfall**: der Event-Bus
fällt auf `FilePollingEventBus` zurück (`config.py`, `EVENT_BUS_BACKEND=auto`),
`utils/signed_ticket.py` auf eine prozessinterne Menge, und `readiness.py` prüft
Redis nur, wenn der Event-Bus ihn nutzt.

`app/jobs/__init__.py` benutzt Redis **gar nicht**: `_BACKEND = "thread"` (`:28`),
und der Modul-Docstring nennt RQ ausdrücklich als Zukunft („Wave 2"). Die Jobs
laufen genau in der Art von Daemon-Threads, die #1472 beschreibt.

## Kosten

| Komponente | Klasse | Was zu tun wäre |
|---|---|---|
| `RunRegistry` | B | `JsonFileStore`-Muster übernehmen (`fcntl.flock`) — im Repo vorhanden |
| `ApiKeysStore` | B | Nachladen einführen oder Cache aufgeben |
| `TaskManager` | B | Rekonstruktion vervollständigen (`progress_detail`) |
| `cancel_flag`, `_start_locks`, `_monitor_generations` | A | geteilte Ablage mit Ablaufmodell und Sperre |
| `_processes`, `_action_queues`, `_stdout_files` | C | **nicht verschiebbar** — nur über Prozessbesitz lösbar |

## Das Verhältnis zu #1472

Beide Vorhaben haben dieselbe Wurzel: Arbeit und ihr Zustand leben im Speicher
und in den Threads des Webprozesses. #1472 beschreibt das aus der Richtung des
Neustarts — ein SIGTERM mitten im Lauf hinterlässt keinen wiederaufnehmbaren
Zustand — und nennt als langfristige Lösung ausdrücklich eine **persistente
Job-Queue mit eigenen Workern**.

Genau das ist die Antwort auf Klasse C. Eine Queue mit eigenen Workern stellt
her, was dort fehlt: **ein Lauf gehört genau einem Prozess**, und dieser Prozess
hält seine Popen-Objekte und Queues, ohne dass jemand anders sie braucht. Ohne
diesen Schritt bliebe Klasse C ungelöst, egal wie viel Zustand man nach Redis
verschiebt.

**Das Anheben von `workers = 1` ist damit keine Vorarbeit zu #1472, sondern
dessen Folge.** Wer vorher Klasse A mehrworker-fähig macht, baut eine geteilte
Ablage für Zustand, den #1472 kurz darauf an einen anderen Ort bringt — und
löst Klasse C dabei trotzdem nicht.

## Entscheidung

1. **`workers = 1` bleibt.** Der HARDSTOP wird nicht angehoben; dieser ADR ist
   der Ort, an dem das nachlesbar ist, statt eines unvollständigen Kommentars in
   der Konfiguration.
2. **#1472 kommt zuerst.** Danach wird neu bewertet, was von Klasse A und B
   überhaupt noch offen ist.
3. **Kein Produktionscode ändert sich** durch diese Entscheidung.

## Konsequenzen

- Der Betrieb bleibt, wie er ist.
- **Ein Einwand gegen die eigene Entscheidung, der benannt gehört:** Es stimmt
  nicht, dass ein zweiter Worker gar nichts brächte. Der Handler von
  `POST /api/graph/ontology/generate` ruft `FileParser.extract_text` synchron im
  Request-Pfad auf ([`api/graph_build.py:221`](../../backend/app/api/graph_build.py)),
  und das ist PyMuPDF — echte CPU-Arbeit im Webprozess, nicht im
  OASIS-Subprozess. Unter einem gevent-Worker blockiert das Hochladen vieler
  oder großer Dokumente alle anderen Anfragen dieses Prozesses. Hier brächte ein
  zweiter Worker tatsächlich Isolation.

  Das ändert die Entscheidung nicht, weil derselbe Effekt billiger zu haben ist,
  indem das Parsen aus dem Request-Pfad wandert — was es mit #1472 ohnehin tut.
  Aber es als „kein Durchsatzgewinn" abzutun wäre falsch.
- Was `workers > 1` darüber hinaus brächte, ist Widerstandsfähigkeit gegen den
  Absturz eines einzelnen Workers. Ein echtes Argument, das heute nur leichter
  wiegt als der doppelte Umbau.
- Was dieser ADR **nicht** klärt: ob die Job-Queue Redis, PostgreSQL oder etwas
  anderes als Rückgrat bekommt. Das gehört zu #1472.
