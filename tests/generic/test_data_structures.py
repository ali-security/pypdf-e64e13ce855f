"""Test the pypdf.generic._data_structures module."""
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, Tuple
from unittest import mock

import pytest

from pypdf import PdfReader, PdfWriter
from pypdf.errors import LimitReachedError, PdfReadError
from pypdf.generic import ArrayObject, ContentStream, DictionaryObject, NameObject, NumberObject, TreeObject
from tests import get_data_from_url

try:
    import resource
except ImportError:
    resource = None

TESTS_ROOT = Path(__file__).parent.parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
RESOURCE_ROOT = PROJECT_ROOT / "resources"


def test_tree_object__cyclic_reference(caplog):
    writer = PdfWriter()
    child1 = writer._add_object(DictionaryObject())
    child2 = writer._add_object(DictionaryObject({NameObject("/Next"): child1}))
    child3 = writer._add_object(DictionaryObject({NameObject("/Next"): child2}))
    child1.get_object()[NameObject("/Next")] = child3
    tree = TreeObject()
    tree[NameObject("/First")] = child2
    tree[NameObject("/Last")] = writer._add_object(DictionaryObject())

    assert list(tree.children()) == [child2.get_object(), child1.get_object(), child3.get_object()]
    assert "Detected cycle in outline structure for " in caplog.text


@pytest.mark.enable_socket
def test_dictionary_object__read_from_stream__limit():
    name = "read_from_stream__length_2gb.pdf"
    url = "https://github.com/user-attachments/files/25842437/read_from_stream__length_2gb.pdf"

    reader = PdfReader(BytesIO(get_data_from_url(url=url, name=name)))
    page = reader.pages[0]

    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Declared stream length of 2147483647 exceeds maximum allowed length\.$"
    ):
        page.extract_text()


def _prepare_test_dictionary_object__read_from_stream__no_limit(
        path: Path
) -> Tuple[str, Dict[str, str], Callable[[], None]]:
    env = os.environ.copy()
    env["COVERAGE_PROCESS_START"] = "pyproject.toml"

    name = "read_from_stream__length_2gb.pdf"
    url = "https://github.com/user-attachments/files/25842437/read_from_stream__length_2gb.pdf"
    data = get_data_from_url(url=url, name=name)
    pdf_path = path / name
    pdf_path.write_bytes(data)
    pdf_path_str = pdf_path.resolve().as_posix()

    try:
        env["PYTHONPATH"] = "." + os.pathsep + env["PYTHONPATH"]
    except KeyError:
        env["PYTHONPATH"] = "."

    def limit_virtual_memory() -> None:
        limit_kb = 1_000_000
        limit_bytes = limit_kb * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

    return pdf_path_str, env, limit_virtual_memory


@pytest.mark.enable_socket
@pytest.mark.skipif(condition=resource is None, reason="Does not have 'resource' module.")
@pytest.mark.skipif(sys.platform == "darwin", reason="RLIMIT_AS is unreliable.")
def test_dictionary_object__read_from_stream__no_limit(tmp_path):
    pdf_path_str, env, limit_virtual_memory = _prepare_test_dictionary_object__read_from_stream__no_limit(tmp_path)

    source_file = tmp_path / "script.py"
    source_file.write_text(
        f"""
import sys
from pypdf import filters, PdfReader

filters.MAX_DECLARED_STREAM_LENGTH = sys.maxsize

with open({pdf_path_str!r}, mode="rb") as fd:
    reader = PdfReader(fd)
    print(reader.pages[0].extract_text())
"""
    )

    result = subprocess.run(  # noqa: S603  # We have the control here.
        [sys.executable, source_file],
        capture_output=True,
        env=env,
        text=True,
        preexec_fn=limit_virtual_memory,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.replace("\r", "").endswith("\nMemoryError\n")


@pytest.mark.enable_socket
@pytest.mark.skipif(condition=resource is None, reason="Does not have 'resource' module.")
@pytest.mark.skipif(sys.platform == "darwin", reason="RLIMIT_AS is unreliable.")
def test_dictionary_object__read_from_stream__no_limit__path(tmp_path):
    pdf_path_str, env, limit_virtual_memory = _prepare_test_dictionary_object__read_from_stream__no_limit(tmp_path)

    source_file = tmp_path / "script.py"
    source_file.write_text(
        f"""
import sys
from pypdf import filters, PdfReader

filters.MAX_DECLARED_STREAM_LENGTH = sys.maxsize

reader = PdfReader({pdf_path_str!r})
print(reader.pages[0].extract_text())
"""
    )

    result = subprocess.run(  # noqa: S603  # We have the control here.
        [sys.executable, source_file],
        capture_output=True,
        env=env,
        text=True,
        preexec_fn=limit_virtual_memory,
    )
    assert result.returncode == 0
    assert result.stdout.replace("\r", "") == "Hello from pypdf\n"
    assert result.stderr == ""


def _get_array_based_buffer(stream_count: int, chunk_bytes: int) -> BytesIO:
    writer = PdfWriter()
    page = writer.add_blank_page(width=10, height=10)

    streams = [ContentStream(stream=None, pdf=writer) for _ in range(stream_count)]
    chunk = b"q\n" + (b"A" * chunk_bytes) + b"\nQ\n"
    [stream.set_data(chunk) for stream in streams]
    contents = ArrayObject([writer._add_object(stream) for stream in streams])
    page[NameObject("/Contents")] = contents

    buffer = BytesIO()
    writer.write(buffer)
    buffer.flush()
    return buffer


@pytest.mark.timeout(10)
def test_content_stream__array_based__performance():
    buffer = _get_array_based_buffer(stream_count=10_000, chunk_bytes=7000)
    reader = PdfReader(buffer)
    _ = reader.pages[0].get_contents()


def test_content_stream__array_based__length():
    buffer = _get_array_based_buffer(stream_count=11_000, chunk_bytes=1)
    reader = PdfReader(buffer)
    with pytest.raises(
            expected_exception=LimitReachedError, match=r"^Array\-based stream has 11000 > 10000 elements\.$"
    ):
        _ = reader.pages[0].get_contents()


@pytest.mark.timeout(10)
def test_content_stream__array_based__output_length():
    buffer = _get_array_based_buffer(stream_count=10_000, chunk_bytes=8192)
    reader = PdfReader(buffer)
    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Array\-based stream has at least 75003501 > 75000000 output bytes\.$"
    ):
        _ = reader.pages[0].get_contents()


@pytest.mark.timeout(5)
def test_dictionary_object__read_from_stream__infinite_loop(caplog):
    data = b"""1 0 obj
<<
<</Length 1 0 R>>
stream
trailer
<< /Size 1 >>
startxref
0
%%EOF
"""
    buffer = BytesIO(data)

    reader = PdfReader(buffer, strict=False)
    with pytest.raises(expected_exception=PdfReadError, match=r"^Cannot find Root object in pdf$"):
        assert len(reader.pages) == 0


def _make_pdf__read_from_stream__limit() -> bytes:
    offsets = []
    pdf = bytearray(b"%PDF-1.4\n")

    def add_obj(n: int, body: bytes) -> None:
        offsets.append((n, len(pdf)))
        pdf.extend(f"{n} 0 obj\n".encode())
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")

    add_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add_obj(3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] /Contents 4 0 R /Resources << >> >>")
    offsets.append((4, len(pdf)))
    pdf.extend(b"4 0 obj\n")
    pdf.extend(b"<< >>\nstream\n")
    pdf.extend(b"A" * 75_000_001)
    pdf.extend(b"\nendstream\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(b"xref\n0 5\n0000000000 65535 f \n")
    offset_map = dict(offsets)
    for n in range(1, 5):
        pdf.extend(f"{offset_map[n]:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(pdf)


@pytest.mark.timeout(5)
def test_dictionary_object__read_from_stream__missing_length__limit() -> None:
    reader = PdfReader(BytesIO(_make_pdf__read_from_stream__limit()))
    page = reader.pages[0]

    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Read stream length of 75000187 exceeds maximum allowed length of 75000000\.$"
    ):
        page.get_contents()


def test_dictionary_object__read_from_stream__read_unsized__limit() -> None:
    reader = PdfReader(RESOURCE_ROOT / "issue-301.pdf")

    with mock.patch.object(DictionaryObject, "_read_unsized_from_stream", return_value=b"dummy") as read_mock:
        obj = reader.get_object(13)
        assert obj is not None
        assert obj == DictionaryObject({
            NameObject("/Filter"): NameObject("/FlateDecode"),
            NameObject("/Length1"): NumberObject(218)
        })
    read_mock.assert_called_once_with(stream=reader.stream, pdf=reader, length=75_000_000)


def test_dictionary_object__read_unsized_from_stream__limit() -> None:
    reader = PdfReader(RESOURCE_ROOT / "issue-301.pdf")

    reader.stream.seek(63101, 0)  # pstart value from the corresponding call
    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Requested length of 236 exceeds maximum allowed length\.$"
    ):
        DictionaryObject._read_unsized_from_stream(stream=reader.stream, pdf=reader, length=137)


def test_content_stream__parse_content_stream__limits() -> None:
    content_stream = ContentStream(stream=None, pdf=None)

    stream = BytesIO(b"/Do TESTING\n")
    content_stream._parse_content_stream(stream)
    assert content_stream.operations == [(["/Do"], b"TESTING")]

    stream = BytesIO(f"/Do {'TESTING' * 100}\n".encode())
    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Read stream length of 240 exceeds maximum allowed length of 128\.$"
    ):
        content_stream._parse_content_stream(stream)
