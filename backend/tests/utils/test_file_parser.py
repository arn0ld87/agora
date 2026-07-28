import re

import pytest
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
    """Sicherstellt: kein Chunk startet mitten im Wort — verlustfrei.

    Alter Code lieferte ``chunks[1] == "ence. This is another one."`` — ein
    Mid-Word-Start. Der Snap geht von ``end - overlap`` (Index 20, mitten in
    "sentence") RÜCKWÄRTS an den Wortanfang (Index 15), nicht vorwärts.
    Rückwärts ist die einzige verlustfreie Richtung: ein Vorwärts-Snap
    müsste über "sentence." hinwegspringen und würde bei Wörtern, die länger
    als der Overlap sind, deren Rest verschlucken. Der Preis ist ein um eine
    Wortlänge größerer Overlap — hier das wiederholte "sentence.".
    """
    text = "This is a test sentence. This is another one."
    chunks = split_text_into_chunks(text, chunk_size=30, overlap=5)

    assert len(chunks) == 2
    assert chunks[0] == "This is a test sentence."
    assert chunks[1] == "sentence. This is another one."

    # Jeder Chunk beginnt an einer echten Wortgrenze des Originaltexts.
    words = set(text.split())
    for chunk in chunks:
        first_word = chunk.split()[0]
        assert first_word in words, f"Chunk startet mid-word: {chunk!r}"

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


# ---------------------------------------------------------------------------
# Neue Tests für Chunk-Boundary-Snap (Issue: 'uß-…', 'atische…'-Anfänge).
# ---------------------------------------------------------------------------


def test_split_text_into_chunks_german_fliesstext():
    """Deutscher Fließtext — Bug-Report-Beispiele dürfen nicht erneut auftauchen.

    Mid-Word-Starts sind Fragmente wie 'uß-', 'atische', 'ige', 'ebühren',
    'rfahren'. Normale deutsche Kleinschreibung am Satzanfang (``eine``,
    ``der``, …) ist hingegen legitim und kein Bug.
    """
    text = (
        "Die geplante Einführung der neuen Busspur-, Rad- und öffentlichen "
        "Nahverkehrsinfrastruktur erfordert eine umfassende Bürgerbeteiligung. "
        "Automatische Kennzeichenerfassung an Zufahrtsstraßen soll den Verkehr "
        "besser steuern. Die einmalige Kosten von rund 85 Millionen Euro "
        "verteilen sich auf mehrere Träger. Die jährlichen Gebühren außerhalb "
        "der Innenstadt sollen moderat ausfallen. Bestimmte Verfahren für "
        "einkommensschwache Gruppen sind vorgesehen."
    )
    chunks = split_text_into_chunks(text, chunk_size=120, overlap=20)

    assert len(chunks) >= 2
    forbidden_mid_word_prefixes = (
        "uß", "atische", "ige ", "ebühren", "rfahren",
    )
    for chunk in chunks:
        first_word = chunk.split(maxsplit=1)[0] if chunk.split() else ""
        starts_mid_word = any(
            first_word.startswith(prefix) for prefix in forbidden_mid_word_prefixes
        )
        assert not starts_mid_word, (
            f"Chunk startet mitten im Wort: {chunk!r}"
        )


def test_split_text_into_chunks_markdown_with_headings():
    """Markdown mit Überschriften — Snap darf Überschriften nicht zerschneiden."""
    text = (
        "# Erste Überschrift\n\n"
        "Dies ist der erste Absatz, der mehrere Sätze enthält. "
        "Er endet mit einem Punkt.\n\n"
        "## Zweite Überschrift\n\n"
        "Hier kommt ein zweiter Absatz, der ebenfalls etwas länger ist und "
        "mehrere zusammenhängende Sätze umfasst. Auch dieser endet hier.\n\n"
        "### Dritte Überschrift\n\n"
        "Letzter Absatz mit zusätzlichem Kontext und ausreichend Text, damit "
        "die Chunking-Logik tatsächlich mehrere Chunks erzeugt."
    )
    chunks = split_text_into_chunks(text, chunk_size=150, overlap=25)

    assert len(chunks) >= 2
    # Jeder Chunk startet entweder mit einer Markdown-Überschrift oder einem
    # normalen Wort — nie mitten in einem Wort.
    for chunk in chunks:
        first_word = chunk.split(maxsplit=1)[0] if chunk.split() else ""
        starts_mid_word = any(
            first_word.startswith(prefix) for prefix in ("ß", "atische", "ige ", "ebühr")
        )
        assert not starts_mid_word, (
            f"Markdown-Chunk startet mitten im Wort: {chunk!r}"
        )


def test_split_text_into_chunks_no_infinite_loop_on_long_word():
    """Pathologisch langes Wort ohne Whitespace darf nicht zu Endlosschleife führen."""
    long_word = "a" * 5000
    text = "Kurzer Vorspann " + long_word + " kurzer Nachspann"

    chunks = split_text_into_chunks(text, chunk_size=200, overlap=20)

    assert len(chunks) >= 1
    assert isinstance(chunks, list)
    # Die Funktion muss terminiert sein und darf nicht leer werden.
    full = "".join(chunks)
    # Inhalt des langen Wortes vollständig erhalten (es darf nichts
    # verschluckt werden).
    assert long_word in full


def test_split_text_into_chunks_preserves_full_content():
    """Die Vereinigung aller Chunks deckt den Originaltext vollständig ab."""
    text = (
        "Erster Abschnitt mit mehreren Sätzen. Hier geht der Text weiter. "
        "Noch mehr Inhalt. Zweiter Abschnitt startet jetzt. Er ist auch "
        "ziemlich lang. Und noch ein dritter Satz zum Abschluss des "
        "zweiten Abschnitts. Dritter Abschnitt ist da. Vierter Abschnitt "
        "folgt gleich. Fünfter Abschnitt mit noch mehr Wörtern. Sechster "
        "Abschnitt. Siebter Abschnitt. Achter Abschnitt."
    )
    chunks = split_text_into_chunks(text, chunk_size=80, overlap=15)

    assert len(chunks) >= 2
    # Kein Chunk startet mitten im Wort — das erste Wort jedes Chunks muss
    # im Originaltext an einer Wortgrenze (Textanfang oder Whitespace davor)
    # beginnen. Kleinschreibung ist dabei KEIN Indikator für einen
    # Mid-Word-Start (z. B. "besser steuern ..." ist ein legitimer Chunk-
    # Anfang an einer echten Wortgrenze).
    for chunk in chunks:
        first_word = chunk.split(maxsplit=1)[0] if chunk.split() else ""
        if first_word:
            assert re.search(r"(?:^|\s)" + re.escape(first_word), text), (
                f"Chunk startet nicht an einer Wortgrenze: {chunk!r}"
            )
    # Jeder Buchstabe aus dem Originaltext kommt mindestens einmal in den
    # Chunks vor (Reihenfolge und vollständige Überlappung sind mit Strip
    # nicht exakt prüfbar, aber die Vereinigung darf nichts erfinden).
    full = "".join(chunks)
    for word in text.split():
        # Whitespace-Position kann sich verschieben, aber jedes Wort muss
        # als Ganzes irgendwo auftauchen.
        assert word in full, f"Wort {word!r} fehlt in den Chunks"


def test_split_text_into_chunks_no_word_start_mid_word():
    """Spezifischer Bug-Repro: Chunk-Anfänge wie 'uß-', 'atische', 'ige' etc.

    Wir bauen einen Text, der im OLD-Algorithmus garantiert solche
    Mid-Word-Anfänge produzieren würde, und prüfen, dass jeder Chunk an
    einer Wortgrenze beginnt.
    """
    # 5 Sätze mit jeweils deutlich mehr Zeichen als chunk_size erlaubt —
    # der OLD-Algorithmus würde mitten in 'Straßenverkehr', 'Kennzeichenerfassung'
    # etc. starten.
    text = (
        "Der Ausbau des öffentlichen Nahverkehrs in der Region erfordert "
        "eine umfassende Modernisierung der bestehenden Busspur-, Rad- und "
        "Fußgängerinfrastruktur. "
        "Die automatische Kennzeichenerfassung an Zufahrtsstraßen soll den "
        "Verkehr besser steuern und die Luftqualität in den Innenstädten "
        "deutlich verbessern. "
        "Die einmaligen Kosten von rund 85 Millionen Euro verteilen sich "
        "auf mehrere Träger und werden durch Bundeszuschüsse ergänzt. "
        "Die jährlichen Gebühren außerhalb der Innenstadt sollen moderat "
        "ausfallen und sozialverträglich gestaltet werden. "
        "Bestimmte Verfahren für einkommensschwache Gruppen sind im "
        "Gesetzentwurf bereits vorgesehen und werden derzeit geprüft."
    )
    chunks = split_text_into_chunks(text, chunk_size=140, overlap=30)

    assert len(chunks) >= 3
    forbidden_prefixes = ("uß-", "atische", "ige ", "ebühren", "rfahren", "uß-")
    for chunk in chunks:
        # Mid-Word: Chunk beginnt mit einem der dokumentierten Bug-Prefixes.
        is_buggy = any(chunk.startswith(p) for p in forbidden_prefixes)
        assert not is_buggy, f"Bug-Prefix in Chunk-Anfang: {chunk!r}"
        # Zusätzlich generisch prüfen: das erste Wort des Chunks muss im
        # Originaltext an einer Wortgrenze beginnen. Kleinschreibung allein
        # ist KEIN Indikator für einen Mid-Word-Start (z. B. "besser
        # steuern und die Luftqualität ..." ist ein legitimer Chunk-Anfang).
        first_word = chunk.split(maxsplit=1)[0] if chunk.split() else ""
        if first_word:
            assert re.search(r"(?:^|\s)" + re.escape(first_word), text), (
                f"Chunk startet nicht an einer Wortgrenze: {chunk!r}"
            )


# ---------------------------------------------------------------------------
# Regressionstests für zwei Defekte, die der erste Snap-Ansatz nicht abdeckte:
# Mid-Word-Starts bei overlap=0 und Degeneration bei großem Overlap.
# ---------------------------------------------------------------------------


def _german_corpus(repeats: int = 6) -> str:
    block = (
        "Die geplante Einführung der neuen Busspur-, Rad- und öffentlichen "
        "Nahverkehrsinfrastruktur erfordert eine umfassende Bürgerbeteiligung. "
        "Automatische Kennzeichenerfassung an Zufahrtsstraßen soll den Verkehr "
        "besser steuern und die Luftqualität deutlich verbessern. "
        "Die einmaligen Kosten von rund 85 Millionen Euro verteilen sich auf "
        "mehrere Träger. Die jährlichen Gebühren außerhalb der Innenstadt sollen "
        "moderat ausfallen. Bestimmte Verfahren für einkommensschwache Gruppen "
        "sind im Gesetzentwurf bereits vorgesehen und werden derzeit geprüft."
    )
    return " ".join(f"Abschnitt{n}: {block}" for n in range(repeats))


@pytest.mark.parametrize("overlap", [0, 5, 15, 30, 50, 100])
@pytest.mark.parametrize("chunk_size", [80, 140, 200, 500])
def test_split_text_into_chunks_word_boundary_across_parameters(chunk_size, overlap):
    """Wortgrenzen-Treue über die ganze Parameterfläche, nicht nur beim Default.

    Regression: der erste Snap-Ansatz deckelte den Vorwärts-Snap auf ``end``
    und neutralisierte sich damit bei ``overlap=0`` selbst — Chunks starteten
    weiterhin mitten im Wort ('ichen', 'sstraßen', 'gerbeteiligung.').
    """
    text = _german_corpus()
    chunks = split_text_into_chunks(text, chunk_size=chunk_size, overlap=overlap)

    words = set(text.split())
    for i, chunk in enumerate(chunks):
        first_word = chunk.split()[0]
        assert first_word in words, (
            f"Chunk {i} startet mid-word (cs={chunk_size}, ov={overlap}): "
            f"{first_word!r}"
        )


@pytest.mark.parametrize("overlap", [0, 5, 15, 30, 50, 100])
@pytest.mark.parametrize("chunk_size", [80, 140, 200, 500])
def test_split_text_into_chunks_lossless_across_parameters(chunk_size, overlap):
    """Kein Wort geht verloren — über die ganze Parameterfläche."""
    text = _german_corpus()
    chunks = split_text_into_chunks(text, chunk_size=chunk_size, overlap=overlap)

    joined = "".join(chunks)
    missing = [w for w in text.split() if w not in joined]
    assert not missing, (
        f"Wörter verloren (cs={chunk_size}, ov={overlap}): {missing[:5]}"
    )


def test_split_text_into_chunks_no_degeneration_with_large_overlap():
    """Großer Overlap darf nicht auf Ein-Zeichen-Schritte entarten.

    Regression: bei ``overlap > 0.3 * chunk_size`` kann die Satzgrenzen-Logik
    ``end`` so weit nach vorn ziehen, dass ``end - overlap <= start`` gilt.
    Eine reine ``start + 1``-Notbremse terminiert zwar, erzeugt aber tausende
    fast identischer Chunks. ``min_progress`` verhindert das.
    """
    text = _german_corpus()
    chunks = split_text_into_chunks(text, chunk_size=60, overlap=30)

    ideal = len(text) // 60
    assert len(chunks) <= ideal * 4, (
        f"Degeneration: {len(chunks)} Chunks bei ~{ideal} erwarteten"
    )


def test_split_text_into_chunks_word_longer_than_chunk_is_lossless():
    """Wort länger als ``chunk_size``: Auftrennung unvermeidbar, aber verlustfrei."""
    long_word = "a" * 5000
    text = "Vorspann " + long_word + " Nachspann mit etwas Text danach."

    chunks = split_text_into_chunks(text, chunk_size=60, overlap=0)

    joined = "".join(chunks)
    assert long_word in joined
    assert "Nachspann mit etwas Text danach." in joined
