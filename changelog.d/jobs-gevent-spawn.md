### Fixed

- Hintergrundarbeit laeuft unter gevent jetzt als Greenlet statt als
  Betriebssystem-Thread. Der Produktionsprozess patcht beim Start alle Sockets
  kooperativ; ein echter Thread brachte seinen eigenen Hub mit und zerlegte
  damit Verbindungen aus den geteilten Pools — sichtbar als abgerissene
  Neo4j-Schreibvorgaenge, als `Response write failure` auf der Datenbankseite
  und als `RemoteDisconnected` beim Aufruf des Sprachmodells. Wiederholungen
  fingen das jedes Mal auf, kosteten aber pro Aufruf Wartezeit. Betroffen
  waren die Job-Verteilung und die drei Hintergrundstarts der Lauf-API.
  Die Protokollzeile der Job-Verteilung nennt zusaetzlich die tatsaechliche
  Ausfuehrungsart, weil `backend=thread` allein den Blick darauf verstellt hat.
