#!/usr/bin/env python3
"""Tests für ``check_legacy_model_picker.py``.

Stdlib-only (kein pytest nötig — ``python3 -m unittest`` reicht). Jeder
Test baut ein eigenes Temp-Verzeichnis mit Fixture-Dateien auf, läuft
den Scanner darüber und assertiert das Ergebnis.

Aufruf
======

    python3 .github/scripts/test_check_legacy_model_picker.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Pfad zum geprüften Script (relativ zu diesem Test)
SCRIPT = Path(__file__).resolve().parent / "check_legacy_model_picker.py"


def _run(target: Path) -> subprocess.CompletedProcess[str]:
    """Ruft das Script mit ``--no-github`` (lokale Plain-Output) auf."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--no-github", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class CheckLegacyModelPickerTests(unittest.TestCase):
    """Fixture-Tests für den v3-Picker-Grep-Check."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    # ------------------------------------------------------------------
    # 1. Komplett sauberes Repo: kein verbotener Import
    # ------------------------------------------------------------------
    def test_clean_tree_returns_zero(self) -> None:
        _write(
            self.root / "components/v4/AiModelPicker.vue",
            "<template><div /></template>\n",
        )
        _write(
            self.root / "store/llmProviders/index.ts",
            "export const x = 1\n",
        )
        _write(
            self.root / "store/llmProfiles/sub.ts",
            "export const y = 2\n",
        )
        _write(
            self.root / "composables/useFoo.ts",
            "import { useLlmProvidersStore } from '@/store/llmProviders/index'\n",
        )

        proc = _run(self.root)
        self.assertEqual(
            proc.returncode,
            0,
            f"erwartet exit 0, got {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )
        self.assertIn("clean", proc.stderr.lower())

    # ------------------------------------------------------------------
    # 2. Verbotene Importe: exit 1, alle sieben Regeln abgedeckt
    # ------------------------------------------------------------------
    def test_dirty_tree_returns_one_with_all_seven_rules(self) -> None:
        _write(
            self.root / "A.vue",
            "import ModelPicker from '@/components/ui/ModelPicker.vue'\n",
        )
        _write(
            self.root / "B.vue",
            "import LlmProfilePicker from '@/components/llm/LlmProfilePicker.vue'\n",
        )
        _write(
            self.root / "C.vue",
            "import ActiveModelBadge from '@/components/ActiveModelBadge.vue'\n",
        )
        _write(
            self.root / "D.ts",
            "import { useLlmProvidersStore } from '@/store/llmProviders'\n",
        )
        _write(
            self.root / "E.ts",
            "import { useLlmProfilesStore } from '@/store/llmProfiles'\n",
        )
        _write(
            self.root / "F.ts",
            "import { useLlmRoutingDefaultsStore } from '@/store/llmRoutingDefaults'\n",
        )
        _write(
            self.root / "G.ts",
            "import { useRuntime } from '@/composables/useRuntimeLlmOptions'\n",
        )

        proc = _run(self.root)
        self.assertEqual(
            proc.returncode,
            1,
            f"erwartet exit 1, got {proc.returncode}\nstderr={proc.stderr}",
        )
        # Alle 7 Regeln müssen im Output auftauchen.
        self.assertIn("ModelPicker.vue", proc.stdout)
        self.assertIn("LlmProfilePicker.vue", proc.stdout)
        self.assertIn("ActiveModelBadge.vue", proc.stdout)
        self.assertIn("store llmProviders", proc.stdout)
        self.assertIn("store llmProfiles", proc.stdout)
        self.assertIn("store llmRoutingDefaults", proc.stdout)
        self.assertIn("useRuntimeLlmOptions", proc.stdout)

    # ------------------------------------------------------------------
    # 3. @deprecated-Ziel: Import eines deprecateten Read-Adapters ist erlaubt
    # ------------------------------------------------------------------
    def test_deprecated_target_allows_import(self) -> None:
        # Ziel-Datei trägt @deprecated → sanktionierter Read-Adapter.
        # Wir verwenden hier useRuntimeLlmOptions.ts als Testobjekt,
        # da Komponenten wie ActiveModelBadge.vue in REMOVED_PATHS stehen
        # und schon bei reiner Existenz blockieren würden.
        _write(
            self.root / "composables/useRuntimeLlmOptions.ts",
            "/** @deprecated Slice 5.5 — Runtime-Credential-Read-Adapter. */\n"
            "export function useRuntimeLlmOptions() {}\n",
        )
        # Consumer ohne jeden Marker importiert das deprecatete Ziel.
        _write(
            self.root / "consumer.vue",
            (
                "<script setup lang=\"ts\">\n"
                "import { useRuntimeLlmOptions } from '@/composables/useRuntimeLlmOptions'\n"
                "</script>\n"
            ),
        )

        proc = _run(self.root)
        self.assertEqual(
            proc.returncode,
            0,
            f"@deprecated-Ziel muss exit 0 ergeben\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )

    # ------------------------------------------------------------------
    # 4. Ziel OHNE @deprecated (oder nicht auflösbar) wird geflaggt
    # ------------------------------------------------------------------
    def test_non_deprecated_target_still_flags(self) -> None:
        # Ziel existiert, trägt aber KEIN @deprecated → Verstoß.
        # Wir verwenden useRuntimeLlmOptions.ts als Testobjekt, damit der Treffer
        # aus der Import-Regel stammt und nicht aus REMOVED_PATHS (wie es bei
        # ActiveModelBadge.vue der Fall wäre).
        _write(
            self.root / "composables/useRuntimeLlmOptions.ts",
            "export function useRuntimeLlmOptions() {}\n",
        )
        _write(
            self.root / "consumer.vue",
            (
                "<script setup lang=\"ts\">\n"
                "import { useRuntimeLlmOptions } from '@/composables/useRuntimeLlmOptions'\n"
                "</script>\n"
            ),
        )
        # Store-Import ohne Ziel-Datei (nach 5.5 gelöscht) → nicht auflösbar → Verstoß.
        _write(
            self.root / "lazy.ts",
            "import { useLlmProvidersStore } from '@/store/llmProviders'\n",
        )
        proc = _run(self.root)
        self.assertEqual(
            proc.returncode,
            1,
            "nicht-deprecatetes Ziel darf nicht durchgehen",
        )
        self.assertIn("useRuntimeLlmOptions", proc.stdout)
        self.assertIn("llmProviders", proc.stdout)

    # ------------------------------------------------------------------
    # 5. Subpfad-Importe sind erlaubt (Zukunftssicherheit)
    # ------------------------------------------------------------------
    def test_subpath_store_imports_are_allowed(self) -> None:
        _write(
            self.root / "future.ts",
            (
                "import { a } from '@/store/llmProviders/index'\n"
                "import { b } from '@/store/llmProviders/sub/deep'\n"
                "import { c } from '@/store/llmProfiles/v2'\n"
                "import { d } from '@/store/llmRoutingDefaults/foo'\n"
            ),
        )
        proc = _run(self.root)
        self.assertEqual(
            proc.returncode,
            0,
            f"Subpfade müssen erlaubt sein\nstdout={proc.stdout}",
        )

    # ------------------------------------------------------------------
    # 6. Relative Imports werden genauso erkannt
    # ------------------------------------------------------------------
    def test_relative_imports_are_caught(self) -> None:
        _write(
            self.root / "x.ts",
            "import { x } from '../store/llmProviders'\n",
        )
        _write(
            self.root / "y.ts",
            "import { y } from '../../components/ui/ModelPicker.vue'\n",
        )
        proc = _run(self.root)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("x.ts", proc.stdout)
        self.assertIn("y.ts", proc.stdout)

    # ------------------------------------------------------------------
    # 7. Usage-Fehler: exit 2 bei unbekanntem Pfad
    # ------------------------------------------------------------------
    def test_unknown_target_returns_two(self) -> None:
        proc = _run(self.root / "does-not-exist")
        self.assertEqual(
            proc.returncode,
            2,
            f"erwartet exit 2, got {proc.returncode}\nstderr={proc.stderr}",
        )
        self.assertIn("usage error", proc.stderr)

    # ------------------------------------------------------------------
    # 8. Entfernte Slice-7.7-Pfade dürfen nicht zurückkehren
    # ------------------------------------------------------------------
    def test_removed_slice_7_7_paths_are_caught(self) -> None:
        removed_paths = (
            "components/ui/ModelPicker.vue",
            "views/Settings/llmRouting/ActiveSnapshotsCard.vue",
            "views/Settings/llmRouting/CustomModelCard.vue",
            "views/Settings/llmRouting/GlobalDefaultCard.vue",
            "views/Settings/llmRouting/StageOverridesCard.vue",
            "views/Settings/llmRouting/mockData.ts",
        )
        for relative_path in removed_paths:
            _write(self.root / relative_path, "// must stay removed\n")

        proc = _run(self.root)

        self.assertEqual(proc.returncode, 1)
        for relative_path in removed_paths:
            self.assertIn(Path(relative_path).name, proc.stdout)

    # ------------------------------------------------------------------
    # 9. Entfernter LlmProfilePicker (Issue #834) darf nicht zurückkehren
    # ------------------------------------------------------------------
    def test_removed_llm_profile_picker_path_is_caught(self) -> None:
        # Reine Datei-Existenz reicht — kein Import nötig. Ein @deprecated-Tag
        # rettet die Datei nicht, weil REMOVED_PATHS vor der Import-Prüfung greift.
        _write(
            self.root / "components/llm/LlmProfilePicker.vue",
            (
                "<script setup lang=\"ts\">\n"
                "/** @deprecated in Issue #834 entfernt. */\n"
                "</script>\n"
            ),
        )

        proc = _run(self.root)

        self.assertEqual(
            proc.returncode,
            1,
            f"zurückgekehrter LlmProfilePicker muss exit 1 ergeben\nstdout={proc.stdout}",
        )
        self.assertIn("LlmProfilePicker.vue", proc.stdout)
        self.assertIn("#834", proc.stdout)

    # ------------------------------------------------------------------
    # 10. GH-Actions-Format: ::error file=…,line=…,col=…
    # ------------------------------------------------------------------
    def test_github_format_emits_annotation(self) -> None:
        _write(
            self.root / "x.ts",
            "import { x } from '@/store/llmProviders'\n",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--github", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GITHUB_ACTIONS": ""},
        )
        self.assertEqual(proc.returncode, 1)
        # Format: ::error file=…,line=N,col=N::MSG
        self.assertIn("::error file=", proc.stdout)
        self.assertIn(",line=", proc.stdout)
        self.assertIn(",col=", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
