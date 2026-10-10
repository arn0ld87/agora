"""CVE-2026-102991: drive URIs must not bypass the Windows template boundary."""

import ntpath
import os
from types import SimpleNamespace

import pytest
from mako import exceptions, template


@pytest.mark.parametrize("uri", ["C:/../../secret.txt", "C:\\..\\..\\secret.txt", "d:/../../secret.txt"])
def test_mako_rejects_drive_traversal_on_windows(monkeypatch, uri):
    # Replace only Mako's module reference; never mutate the process-wide os.path.
    windows_os = SimpleNamespace(**{**vars(os), "path": ntpath})
    monkeypatch.setattr(template, "os", windows_os)

    with pytest.raises(exceptions.TemplateLookupException, match="invalid"):
        template.Template(text="safe", uri=uri)


def test_mako_still_renders_valid_template():
    assert template.Template(text="Hello ${name}", uri="ok.html").render(name="Agora") == "Hello Agora"
