import os
import pytest
from pathlib import Path
from app.utils.file_parser import FileParser, _read_text_with_fallback, split_text_into_chunks

def test_read_text_with_fallback_utf8(tmp_path):
    file_path = tmp_path / "test_utf8.txt"
    content = "Hello, world! Ümlaut"
    file_path.write_text(content, encoding="utf-8")

    result = _read_text_with_fallback(str(file_path))
    assert result == content

def test_read_text_with_fallback_latin1(tmp_path):
    file_path = tmp_path / "test_latin1.txt"
    content = "Hello, world! Umlaut"
    file_path.write_bytes(content.encode("iso-8859-1"))

    result = _read_text_with_fallback(str(file_path))
    assert result == content

def test_split_text_into_chunks_simple():
    text = "This is a test sentence. This is another one."
    chunks = split_text_into_chunks(text, chunk_size=30, overlap=5)

    assert len(chunks) == 2
    assert chunks[0] == "This is a test sentence."
    # start = 24 (end of first chunk) - 5 (overlap) = 19
    # text[19:] = "ence. This is another one."
    # Wait, 'This is a test sentence.' is 24 chars long.
    # index 24 is space after '.'
    # if it split at '.', then end = 24.
    # start = 24 - 5 = 19.
    # text[19:19+10] = "ence."
    assert chunks[1] == "nce. This is another one."

def test_split_text_into_chunks_small_text():
    text = "Short text."
    chunks = split_text_into_chunks(text, chunk_size=100)
    assert chunks == ["Short text."]

def test_split_text_into_chunks_empty():
    assert split_text_into_chunks("") == []
    assert split_text_into_chunks("   ") == []

def test_extract_text_txt(tmp_path):
    file_path = tmp_path / "test.txt"
    content = "Plain text content"
    file_path.write_text(content)

    result = FileParser.extract_text(str(file_path))
    assert result == content

def test_extract_text_md(tmp_path):
    file_path = tmp_path / "test.md"
    content = "# Heading\n\nMarkdown content"
    file_path.write_text(content)

    result = FileParser.extract_text(str(file_path))
    assert result == content

def test_extract_text_unsupported(tmp_path):
    file_path = tmp_path / "test.exe"
    file_path.write_text("binary")

    with pytest.raises(ValueError, match="Unsupported file format"):
        FileParser.extract_text(str(file_path))

def test_extract_text_not_found():
    with pytest.raises(FileNotFoundError):
        FileParser.extract_text("non_existent_file.txt")

def test_extract_from_multiple(tmp_path):
    f1 = tmp_path / "f1.txt"
    f1.write_text("content 1")
    f2 = tmp_path / "f2.md"
    f2.write_text("content 2")

    result = FileParser.extract_from_multiple([str(f1), str(f2)])
    assert "=== Document 1: f1.txt ===" in result
    assert "content 1" in result
    assert "=== Document 2: f2.md ===" in result
    assert "content 2" in result

def test_extract_from_multiple_with_failure(tmp_path):
    f1 = tmp_path / "f1.txt"
    f1.write_text("content 1")

    result = FileParser.extract_from_multiple([str(f1), "non_existent.txt"])
    assert "=== Document 1: f1.txt ===" in result
    assert "=== Document 2: non_existent.txt (extraction failed:" in result
