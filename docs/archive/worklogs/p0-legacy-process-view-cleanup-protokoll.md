# P0-Protokoll — Legacy Cleanup `Process.vue`

## Ausgangslage
Nach der Migration des eigentlichen Process-Workflows auf `frontend/src/views/MainView.vue` blieb die frühere Datei `frontend/src/views/Process.vue` noch im Repository liegen.

Der Router nutzte zu diesem Zeitpunkt bereits **nicht mehr** die alte Datei, sondern importierte:

```js
import Process from '../views/MainView.vue'
```

Damit war `Process.vue` nur noch ein verwaistes Alt-Artefakt:
- groß (~52 KB)
- nicht mehr über den Router eingebunden
- irreführend, weil Dateiname und tatsächliche Runtime-Route auseinanderliefen

## Ziel
- Altlast entfernen, solange keine Runtime-Referenz mehr existiert
- Router lesbarer machen
- Kompatibilität der Route `name: 'Process'` und des Pfads `/process/:projectId` vollständig erhalten

## Umsetzung

### 1. Router-Bezeichner klargestellt
**Datei:** `frontend/src/router/index.js`

Änderung:
- Importalias von `Process` auf `MainView` umbenannt
- Routenobjekt nutzt jetzt `component: MainView`

Wichtig:
- nur der lokale Importname wurde präzisiert
- `name: 'Process'` blieb unverändert
- der URL-Pfad `/process/:projectId` blieb unverändert

### 2. Tote Legacy-Datei entfernt
**Datei entfernt:** `frontend/src/views/Process.vue`

Begründung:
- keine Router-Nutzung mehr
- keine verbleibenden Importreferenzen
- alte Implementierung hätte die neue Workspace-Shell eher wieder verwässert als genutzt

## Verifikation
- Code-Suche auf verbleibende `Process.vue`-Direktverweise → **keine Treffer**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → **bestanden**

## Ergebnis
Die Runtime bleibt identisch, aber das Frontend ist jetzt konsistenter:
- eine eindeutige aktive Process-View (`MainView.vue`)
- keine tote Parallelimplementierung mehr
- klarerer Router-Code ohne historisch irreführenden Alias
