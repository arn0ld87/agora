Der HARDSTOP `workers = 1` im Produktions-Gunicorn ist nicht mehr nur ein
Kommentar in der Konfiguration, sondern in ADR-0015 beziffert — und der
Kommentar erwies sich dabei als unvollständig.

Der prozesslokale Zustand zerfällt in drei Klassen: verschiebbare Datenwerte
ohne geteilten Ort, Fälle mit vorhandener Ablage, denen nur Cache oder Sperre
fehlen, und **nicht verschiebbare** Betriebssystem-Handles — Popen-Objekte,
In-Prozess-Queues und offene Dateideskriptoren im `SimulationRunner`. Die dritte
Klasse ist durch keine geteilte Ablage lösbar, sondern nur dadurch, dass genau
ein Prozess einen Lauf besitzt. Genau das liefert die persistente Job-Queue mit
eigenen Workern aus #1472; das Anheben von `workers = 1` ist dessen Folge, keine
Vorarbeit.

Kein Produktionscode geändert.
