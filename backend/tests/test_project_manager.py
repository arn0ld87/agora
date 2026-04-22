from pathlib import Path

import pytest

from app.models.project import ProjectManager, ProjectStatus


class DummyFileStorage:
    def __init__(self, content: bytes):
        self._content = content

    def save(self, path):
        Path(path).write_bytes(self._content)


@pytest.fixture
def isolated_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    return Path(ProjectManager.PROJECTS_DIR)


def test_create_save_load_and_delete_project(isolated_projects_dir):
    project = ProjectManager.create_project(name="Test Project")
    assert project.status == ProjectStatus.CREATED

    project.simulation_requirement = "Analyse community reactions"
    ProjectManager.save_project(project)

    loaded = ProjectManager.get_project(project.project_id)
    assert loaded is not None
    assert loaded.name == "Test Project"
    assert loaded.simulation_requirement == "Analyse community reactions"

    deleted = ProjectManager.delete_project(project.project_id)
    assert deleted is True
    assert ProjectManager.get_project(project.project_id) is None


def test_save_file_to_project_stores_file_inside_project_directory(isolated_projects_dir):
    project = ProjectManager.create_project(name="Uploads")
    file_storage = DummyFileStorage(b"hello agora")

    file_info = ProjectManager.save_file_to_project(
        project.project_id,
        file_storage,
        "../unsafe-name.md",
    )

    saved_path = Path(file_info["path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"hello agora"
    assert saved_path.suffix == ".md"
    assert saved_path.is_relative_to(isolated_projects_dir)
    assert ".." not in file_info["saved_filename"]


def test_save_file_to_project_rejects_invalid_project_id(isolated_projects_dir):
    file_storage = DummyFileStorage(b"test")

    with pytest.raises(ValueError, match="Invalid project_id"):
        ProjectManager.save_file_to_project(
            "not-a-project-id",
            file_storage,
            "notes.txt",
        )
