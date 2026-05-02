"""Settings-Layer (Issue #133).

Implementiert die in der Akzeptanz geforderte Lade-Reihenfolge

    Defaults → .env (``os.environ``) → instance/settings.json
             → in-memory Override

und liefert pro Feld den effektiven Wert plus die Quelle, aus der er
stammt (``default``/``env``/``file``/``override``). Letzter gewinnt.

In SUB1 ist der Layer schreibgeschützt: Override ist initial leer und
wird erst von SUB2 (PUT-Endpoint) befüllt; ``instance/settings.json``
wird nur gelesen. Trotzdem wird die volle Lade-Logik schon hier
implementiert, damit die GET-API in SUB1 Sources ehrlich anzeigt und
SUB2 nur den Schreibpfad ergänzt.

Threading: Der Layer ist nicht reentrant — Flask läuft per Default mit
einem Worker-Thread pro Request, und ``set_override``/``persist_to_file``
(SUB2) werden über einen einfachen Lock serialisiert. Für SUB1 reicht
ein nüchterner Read-Path.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .settings_schema import (
    SECTIONS,
    SETTINGS_FIELDS,
    FieldSpec,
    field_by_key,
)


# Source-Konstanten — als Strings stabilisiert, weil sie Bestandteil
# des API-Contracts sind (Frontend-Tests greifen sie 1:1 ab).
SOURCE_DEFAULT = 'default'
SOURCE_ENV = 'env'
SOURCE_FILE = 'file'
SOURCE_OVERRIDE = 'override'


def default_instance_path() -> Path:
    """Pfad zur ``instance/settings.json``.

    Liegt unter ``backend/instance/settings.json`` — analog zu Flasks
    Standard-`instance`-Konvention. Der Pfad wird hier zentral
    aufgelöst, damit Tests via ``SettingsService(instance_path=…)``
    den Speicherort patchen können.
    """
    return Path(__file__).resolve().parent.parent.parent / 'instance' / 'settings.json'


class SettingsService:
    """Liest die vier Layer und liefert pro Feld den effektiven Wert.

    Eine Instanz wird in :func:`get_default_service` als Modul-Singleton
    gehalten, damit das in-memory Override über Requests hinweg lebt.
    Tests bauen ihre eigene Instanz mit eigenem ``instance_path``.
    """

    def __init__(self, instance_path: Path | None = None) -> None:
        self._instance_path = Path(instance_path) if instance_path else default_instance_path()
        self._override: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lese-Pfade
    # ------------------------------------------------------------------

    def _read_file_layer(self) -> dict[str, Any]:
        """Liefert den Inhalt von ``instance/settings.json`` als Dict.

        Returns ``{}``, wenn die Datei fehlt oder corrupted ist — der
        Bootstrapping-Pfad soll auch dann sauber laufen, wenn das
        Override-File noch nie geschrieben wurde. Korrupte JSON wird
        als leer behandelt; SUB2 schreibt atomar, sodass der Fall in
        Praxis nur bei manuellem Editieren auftritt.
        """
        try:
            raw = self._instance_path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return {}
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _coerce(self, spec: FieldSpec, raw_value: Any) -> Any:
        """Wandelt einen rohen Wert (env-string oder JSON-Native) in
        den Schema-Typ um.

        ``os.environ``-Werte sind immer Strings; ``instance/settings.json``
        liefert bereits native Typen aus JSON. Wir vereinheitlichen
        beides hier, damit der GET-Response konsistente Typen ausweist.
        """
        if raw_value is None:
            return None

        if spec.type == 'string' or spec.type == 'enum':
            return str(raw_value)
        if spec.type == 'int':
            try:
                return int(raw_value)
            except (TypeError, ValueError):
                return spec.default
        if spec.type == 'float':
            try:
                return float(raw_value)
            except (TypeError, ValueError):
                return spec.default
        if spec.type == 'bool':
            if isinstance(raw_value, bool):
                return raw_value
            return str(raw_value).strip().lower() in ('true', '1', 'yes', 'on')
        return raw_value

    def _resolve_field(
        self,
        spec: FieldSpec,
        file_layer: dict[str, Any],
    ) -> tuple[Any, str, bool]:
        """Liefert ``(effective_value, source, is_set)`` für ein Feld.

        ``is_set`` ist ``True``, sobald irgendeine Quelle (env/file/
        override) den Wert explizit gesetzt hat — wichtig für das
        ``is_set``-Flag bei Secrets, das im GET-Response statt des
        Klartextes erscheint.
        """
        # 1. Override gewinnt
        if spec.key in self._override:
            return (
                self._coerce(spec, self._override[spec.key]),
                SOURCE_OVERRIDE,
                True,
            )

        # 2. instance/settings.json
        if spec.key in file_layer:
            return (
                self._coerce(spec, file_layer[spec.key]),
                SOURCE_FILE,
                True,
            )

        # 3. Env (process environment)
        env_raw = os.environ.get(spec.key)
        if env_raw is not None and env_raw != '':
            return (self._coerce(spec, env_raw), SOURCE_ENV, True)

        # 4. Default
        return (spec.default, SOURCE_DEFAULT, False)

    # ------------------------------------------------------------------
    # Public API (read-only in SUB1)
    # ------------------------------------------------------------------

    def get_field_state(self, key: str) -> dict[str, Any] | None:
        """Liefert den vollen GET-Response-Eintrag für ein einzelnes Feld
        oder ``None``, wenn der Key nicht im Schema steht.
        """
        spec = field_by_key(key)
        if spec is None:
            return None
        return self._field_payload(spec, self._read_file_layer())

    def get_all_grouped(self) -> dict[str, list[dict[str, Any]]]:
        """Liefert alle Felder gruppiert nach Sektion. Reihenfolge der
        Sektionen folgt :data:`SECTIONS`, Reihenfolge der Felder
        innerhalb einer Sektion folgt :data:`SETTINGS_FIELDS`.
        """
        file_layer = self._read_file_layer()
        grouped: dict[str, list[dict[str, Any]]] = {sec: [] for sec in SECTIONS}
        for spec in SETTINGS_FIELDS:
            grouped[spec.section].append(self._field_payload(spec, file_layer))
        return grouped

    def get_schema(self) -> list[dict[str, Any]]:
        """Liefert nur Meta-Daten (kein Wert, keine Source) — für das
        Frontend-Form-Render. Defaults sind dabei bewusst enthalten,
        damit das Frontend einen `Reset`-Hinweis anzeigen kann.
        Secrets-Defaults werden hier nie ausgespielt: bei
        ``secret=True`` ersetzt der Endpoint den Default durch ``None``.
        """
        out: list[dict[str, Any]] = []
        for spec in SETTINGS_FIELDS:
            entry: dict[str, Any] = {
                'key': spec.key,
                'section': spec.section,
                'type': spec.type,
                'secret': spec.secret,
                'reload_required': spec.reload_required,
                'default': None if spec.secret else spec.default,
            }
            if spec.enum_values is not None:
                entry['enum_values'] = list(spec.enum_values)
            if spec.min_value is not None:
                entry['min'] = spec.min_value
            if spec.max_value is not None:
                entry['max'] = spec.max_value
            if spec.cross_validates_with:
                entry['cross_validates_with'] = list(spec.cross_validates_with)
            out.append(entry)
        return out

    # ------------------------------------------------------------------
    # Override-Hooks (SUB2 wird sie über die PUT-Route befüllen)
    # ------------------------------------------------------------------

    def set_override(self, key: str, value: Any) -> None:
        """In-memory Override setzen. Wirft ``KeyError`` für unbekannte
        Felder. Die eigentliche Validierung gegen Typ/Range geschieht
        in SUB2 vor dem Aufruf — hier nur Schema-Existenz.
        """
        if field_by_key(key) is None:
            raise KeyError(f'unknown settings key: {key}')
        with self._lock:
            self._override[key] = value

    def clear_override(self, key: str | None = None) -> None:
        """Override für ein einzelnes Feld (oder alle, wenn ``key=None``)
        wieder leeren. Wird von SUB2 für Reset-Aktionen genutzt.
        """
        with self._lock:
            if key is None:
                self._override.clear()
            else:
                self._override.pop(key, None)

    @property
    def instance_path(self) -> Path:
        return self._instance_path

    # ------------------------------------------------------------------
    # Schreibpfad (SUB2)
    # ------------------------------------------------------------------

    def apply_payload(
        self,
        payload: dict[str, Any],
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Akzeptierte und bereits validierte Werte ins File und in das
        in-memory Override schreiben.

        ``payload`` muss bereits durch
        :func:`settings_validator.validate_payload` gegangen sein —
        diese Methode validiert nicht, sondern persistiert. So bleibt
        ein klarer „validate first, write second"-Vertrag und der
        Service hat keine Doppel-Validation.

        Wenn ``persist=True``, wird ``instance/settings.json`` atomar
        überschrieben (alle in der File-Layer bereits vorhandenen
        Felder bleiben erhalten und werden vom Payload nur gemerged,
        nicht ersetzt). Das in-memory Override wird *immer* gesetzt,
        damit der Live-Wert auch ohne Reload sichtbar ist (UI nutzt
        ``reload_required``-Flag, um auf Restart-Notwendigkeit
        hinzuweisen).

        Returns das gemergte File-Layer-Dict (für Tests / Logging).
        """
        if not payload:
            return self._read_file_layer()

        with self._lock:
            # In-memory Override aktualisieren — mit den bereits
            # gecasteten Werten aus ``payload``. Damit zeigt GET sofort
            # die neuen Werte mit ``source=override`` (bzw. ``file``,
            # falls persist=True und nichts anderes überschreibt).
            for key, value in payload.items():
                self._override[key] = value

            if persist:
                file_layer = self._read_file_layer()
                file_layer.update(payload)
                self._write_file_layer_atomic(file_layer)
                # Override entfernen, weil File jetzt die persistierte
                # Wahrheit ist und der Source-Resolver zuerst File
                # prüft. Das hält die UI-Anzeige konsistent
                # (``source: file`` statt ``override`` nach Persist).
                for key in payload:
                    self._override.pop(key, None)
                return file_layer

        return self._read_file_layer()

    def remove_persisted(self, keys: list[str]) -> dict[str, Any]:
        """Entfernt Keys aus ``instance/settings.json`` (Reset-auf-Default).

        Schreibt atomar; erzeugt die Datei nicht neu, wenn nach dem
        Remove nichts mehr übrig wäre und sie noch gar nicht existierte.
        """
        if not keys:
            return self._read_file_layer()
        with self._lock:
            file_layer = self._read_file_layer()
            removed = False
            for key in keys:
                if key in file_layer:
                    file_layer.pop(key)
                    removed = True
                self._override.pop(key, None)
            if removed or self._instance_path.exists():
                self._write_file_layer_atomic(file_layer)
            return file_layer

    def _write_file_layer_atomic(self, data: dict[str, Any]) -> None:
        """Schreibt ``data`` als JSON nach :pyattr:`instance_path` —
        atomar, via ``tmp`` + ``os.replace``.

        ``os.replace`` ist auf POSIX und Windows atomar, solange Quelle
        und Ziel auf demselben Filesystem liegen. Wir benutzen
        :func:`tempfile.NamedTemporaryFile` mit ``delete=False`` im
        Zielverzeichnis — so kann ein Crash zwischen ``write`` und
        ``replace`` höchstens eine zurückgelassene tmp-Datei
        produzieren, niemals eine korrupte ``settings.json``.
        """
        target = self._instance_path
        target.parent.mkdir(parents=True, exist_ok=True)
        # NamedTemporaryFile schreibt im Zielverzeichnis — wichtig für
        # Atomicity (gleiches Filesystem). Suffix ``.tmp`` macht
        # Reste nach Crashes leichter erkennbar.
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=str(target.parent),
            prefix='settings.',
            suffix='.json.tmp',
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(data, tmp, ensure_ascii=False, indent=2, sort_keys=True)
            tmp.write('\n')
            tmp.flush()
            try:
                # ``fsync`` ist optional — auf Btrfs (alex' Default)
                # erhöht es den Schutz gegen Power-Loss-Korruption.
                os.fsync(tmp.fileno())
            except OSError:
                # Manche Filesysteme (z. B. einige Test-Mounts)
                # mögen kein fsync — wir tolerieren das, atomic
                # rename hängt nicht davon ab.
                pass
        os.replace(tmp_path, target)

    # ------------------------------------------------------------------
    # Interna
    # ------------------------------------------------------------------

    def _field_payload(
        self,
        spec: FieldSpec,
        file_layer: dict[str, Any],
    ) -> dict[str, Any]:
        value, source, is_set = self._resolve_field(spec, file_layer)
        payload: dict[str, Any] = {
            'key': spec.key,
            'section': spec.section,
            'type': spec.type,
            'secret': spec.secret,
            'reload_required': spec.reload_required,
            'source': source,
            'is_set': is_set,
        }
        if spec.enum_values is not None:
            payload['enum_values'] = list(spec.enum_values)
        if spec.secret:
            # Secrets werden im GET nie als Klartext ausgeliefert —
            # auch dann nicht, wenn sie gerade per Override gesetzt
            # wurden. Frontend nutzt ``is_set`` als Indikator.
            payload['value'] = None
        else:
            payload['value'] = value
            payload['default'] = spec.default
        return payload


# Modul-weiter Singleton — die Flask-App nutzt ``get_default_service()``
# in den Routes, sodass das in-memory Override über Requests hinweg
# erhalten bleibt. Tests bauen sich eigene ``SettingsService``-Instanzen
# und müssen den Singleton nicht anfassen.
_default_service: SettingsService | None = None
_default_service_lock = threading.Lock()


def get_default_service() -> SettingsService:
    global _default_service
    if _default_service is None:
        with _default_service_lock:
            if _default_service is None:
                _default_service = SettingsService()
    return _default_service


def reset_default_service_for_tests() -> None:
    """Test-Hook: Singleton zurücksetzen. Nicht in Produktionscode
    aufrufen.
    """
    global _default_service
    with _default_service_lock:
        _default_service = None
