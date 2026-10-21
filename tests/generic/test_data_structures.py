"""Test the pypdf.generic._data_structures module."""
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, Tuple

import pytest

from pypdf import PdfReader, PdfWriter
from pypdf.errors import LimitReachedError
from pypdf.generic import DictionaryObject, NameObject, TreeObject
from tests import get_data_from_url

try:
    import resource
except ImportError:
    resource = None


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
