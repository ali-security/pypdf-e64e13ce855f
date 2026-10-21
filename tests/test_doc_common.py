"""Test the pypdf._doc_common module."""
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

from pypdf import PdfReader, PdfWriter
from pypdf.errors import LimitReachedError, PdfReadError
from pypdf.filters import FlateDecode
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    EmbeddedFile,
    EncodedStreamObject,
    NameObject,
    NullObject,
    TextStringObject,
    ViewerPreferences,
)
from tests import get_data_from_url

TESTS_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TESTS_ROOT.parent
SAMPLE_ROOT = PROJECT_ROOT / "sample-files"
RESOURCES_ROOT = PROJECT_ROOT / "resources"

PDFATTACH_BINARY = shutil.which("pdfattach")


@pytest.mark.skipif(PDFATTACH_BINARY is None, reason="Requires poppler-utils")
def test_attachments(tmpdir):
    # No attachments.
    clean_path = SAMPLE_ROOT / "002-trivial-libre-office-writer" / "002-trivial-libre-office-writer.pdf"
    with PdfReader(clean_path) as pdf:
        assert pdf._list_attachments() == []
        assert list(pdf.attachment_list) == []

    # UF = name.
    attached_path = tmpdir / "attached.pdf"
    file_path = tmpdir / "test.txt"
    file_path.write_binary(b"Hello World\n")
    subprocess.run([PDFATTACH_BINARY, clean_path, file_path, attached_path])  # noqa: S603
    with PdfReader(str(attached_path)) as pdf:
        assert pdf._list_attachments() == ["test.txt"]
        assert pdf._get_attachments("test.txt") == {"test.txt": b"Hello World\n"}
        assert [(x.name, x.content) for x in pdf.attachment_list] == [("test.txt", b"Hello World\n")]
        assert next(pdf.attachment_list).alternative_name == "test.txt"

    # UF != name.
    different_path = tmpdir / "different.pdf"
    different_path.write_binary(re.sub(rb" /UF [^/]+ /", b" /UF(my-file.txt) /", attached_path.read_binary()))
    with PdfReader(str(different_path)) as pdf:
        assert pdf._list_attachments() == ["test.txt", "my-file.txt"]
        assert pdf._get_attachments("test.txt") == {"test.txt": b"Hello World\n"}
        assert pdf._get_attachments("my-file.txt") == {"my-file.txt": b"Hello World\n"}
        assert [(x.name, x.content) for x in pdf.attachment_list] == [("test.txt", b"Hello World\n")]
        assert next(pdf.attachment_list).alternative_name == "my-file.txt"

    # Only name.
    no_f_path = tmpdir / "no-f.pdf"
    no_f_path.write_binary(re.sub(rb" /UF [^/]+ /", b" /", attached_path.read_binary()))
    with PdfReader(str(no_f_path)) as pdf:
        assert pdf._list_attachments() == ["test.txt"]
        assert pdf._get_attachments("test.txt") == {"test.txt": b"Hello World\n"}
        assert [(x.name, x.content) for x in pdf.attachment_list] == [("test.txt", b"Hello World\n")]
        assert next(pdf.attachment_list).alternative_name is None

    # UF and F.
    uf_f_path = tmpdir / "uf-f.pdf"
    uf_f_path.write_binary(attached_path.read_binary().replace(b" /UF ", b"/F(file.txt) /UF "))
    with PdfReader(str(uf_f_path)) as pdf:
        assert pdf._list_attachments() == ["test.txt"]
        assert pdf._get_attachments("test.txt") == {"test.txt": b"Hello World\n"}
        assert [(x.name, x.content) for x in pdf.attachment_list] == [("test.txt", b"Hello World\n")]
        assert next(pdf.attachment_list).alternative_name == "test.txt"

    # Only F.
    only_f_path = tmpdir / "f.pdf"
    only_f_path.write_binary(attached_path.read_binary().replace(b" /UF ", b" /F "))
    with PdfReader(str(only_f_path)) as pdf:
        assert pdf._list_attachments() == ["test.txt"]
        assert pdf._get_attachments("test.txt") == {"test.txt": b"Hello World\n"}
        assert [(x.name, x.content) for x in pdf.attachment_list] == [("test.txt", b"Hello World\n")]
        assert next(pdf.attachment_list).alternative_name == "test.txt"


def test_get_attachments__same_attachment_more_than_twice():
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    for i in range(5):
        writer.add_attachment("test.txt", f"content{i}")
    assert writer._get_attachments("test.txt") == {
        "test.txt": [b"content0", b"content1", b"content2", b"content3", b"content4"]
    }
    assert [(x.name, x.content) for x in writer.attachment_list] == [
        ("test.txt", b"content0"),
        ("test.txt", b"content1"),
        ("test.txt", b"content2"),
        ("test.txt", b"content3"),
        ("test.txt", b"content4"),
    ]


def test_get_attachments__alternative_name_is_none():
    writer = PdfWriter()
    attachment = EmbeddedFile(name="test.txt", pdf_object=writer.root_object)
    assert attachment.alternative_name is None
    with mock.patch(
            "pypdf._writer.PdfWriter.attachment_list",
            new_callable=mock.PropertyMock(return_value=[attachment])
    ), mock.patch(
            "pypdf.generic._files.EmbeddedFile.content",
            new_callable=mock.PropertyMock(return_value=b"content")
    ):
        assert writer._get_attachments() == {"test.txt": b"content"}


@pytest.mark.enable_socket
def test_byte_encoded_named_destinations():
    url = "https://github.com/user-attachments/files/19820164/pypdf_issue.pdf"
    name = "issue3261.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url=url, name=name)))

    page = reader.pages[0]
    for annotation in page.annotations:
        if annotation.get("/Subtype") == "/Link":
            action = annotation["/A"]
            if action["/S"] == "/GoTo":
                named_dest = action["/D"]
                assert str(named_dest) in reader.named_destinations

    assert reader.named_destinations == {
        "Doc-Start": {
            "/Title": "Doc-Start",
            "/Page": page.indirect_reference,
            "/Type": "/XYZ",
            "/Left": 133.768,
            "/Top": 667.198,
            "/Zoom": NullObject()
        },
        "楣整搮捡귃㉫㈰爵捡牥汦杩瑨敷杩瑨瑳瑡捩慤慴": {
            "/Title": "楣整搮捡귃㉫㈰爵捡牥汦杩瑨敷杩瑨瑳瑡捩慤慴",
            "/Page": page.indirect_reference,
            "/Type": "/XYZ",
            "/Left": 133.768,
            "/Top": 614.424,
            "/Zoom": NullObject()
        },
        "page.1": {
            "/Title": "page.1",
            "/Page": page.indirect_reference,
            "/Type": "/XYZ",
            "/Left": 132.768,
            "/Top": 705.06,
            "/Zoom": NullObject()
        },
        "section*.1": {
            "/Title": "section*.1",
            "/Page": page.indirect_reference,
            "/Type": "/XYZ",
            "/Left": 133.768,
            "/Top": 642.222,
            "/Zoom": NullObject()
        }
    }


def test_viewer_preferences__indirect_reference():
    input_path = RESOURCES_ROOT / "git.pdf"
    reader = PdfReader(input_path)
    assert (0, 24) not in reader.resolved_objects
    viewer_preferences = reader.viewer_preferences
    assert isinstance(viewer_preferences, ViewerPreferences)
    assert viewer_preferences == {"/DisplayDocTitle": True}
    assert (0, 24) in reader.resolved_objects
    assert id(viewer_preferences) == id(reader.viewer_preferences)
    assert id(viewer_preferences) == id(reader.resolved_objects[(0, 24)])


@pytest.mark.enable_socket
def test_named_destinations__tree_is_null_object():
    url = "https://github.com/user-attachments/files/20885216/test.pdf"
    name = "issue3330.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url=url, name=name)))

    assert reader.named_destinations == {}


def test_flatten__cyclic_references():
    path = RESOURCES_ROOT / "crazyones.pdf"

    reader = PdfReader(path)
    assert len(reader.pages) == 1
    reader._flatten()

    # Make the first child point to the object itself.
    pages_object = reader.get_object(10)
    pages_object[NameObject("/Kids")][0].indirect_reference.idnum = 10
    reader.resolved_objects[(10, 0)] = pages_object

    with pytest.raises(expected_exception=PdfReadError, match=r"^Detected cyclic page references\.$"):
        reader._flatten()


@pytest.mark.enable_socket
@pytest.mark.timeout(10)
def test_get_outline__cyclic_references(caplog):
    url = "https://github.com/user-attachments/files/24859044/circular_outline.pdf"
    name = "circular_outline.pdf"
    reader = PdfReader(BytesIO(get_data_from_url(url=url, name=name)))

    assert reader.outline == [
        {
            "/%is_open%": True,
            "/Page": reader.pages[0].indirect_reference,
            "/Title": "Bookmark A",
            "/Type": "/Fit"
        },
        {
            "/%is_open%": True,
            "/Page": reader.pages[0].indirect_reference,
            "/Title": "Bookmark B",
            "/Type": "/Fit"
        }
    ]
    assert caplog.messages[0].startswith("Detected cycle in outline structure for {")


@pytest.mark.enable_socket
@pytest.mark.timeout(10)
def test_get_outline__cyclic_references__nested_handling(caplog):
    url = "https://github.com/user-attachments/files/24859044/circular_outline.pdf"
    name = "circular_outline.pdf"
    writer = PdfWriter(clone_from=BytesIO(get_data_from_url(url=url, name=name)))

    nested_outline = DictionaryObject()
    writer._add_object(nested_outline)
    nested_outline.update({
        NameObject("/Title"): TextStringObject("Nested entry"),
        NameObject("/Parent"): writer.get_object(5),
        NameObject("/Dest"): ArrayObject([writer.pages[0].indirect_reference, NameObject("/Fit")]),
        NameObject("/Next"): writer.get_object(6),
    })
    writer.get_object(5)[NameObject("/First")] = nested_outline.indirect_reference
    writer.get_object(6)[NameObject("/First")] = nested_outline.indirect_reference

    assert writer.outline == [
        {
            "/%is_open%": True,
            "/Page": writer.pages[0].indirect_reference,
            "/Title": "Bookmark A",
            "/Type": "/Fit"
        },
        [
            {
                "/%is_open%": True,
                "/Page": writer.pages[0].indirect_reference,
                "/Title": "Nested entry",
                "/Type": "/Fit"
            },
            {
                "/%is_open%": True,
                "/Page": writer.pages[0].indirect_reference,
                "/Title": "Bookmark B",
                "/Type": "/Fit"
            }
        ],
        {
            "/%is_open%": True,
            "/Page": writer.pages[0].indirect_reference,
            "/Title": "Bookmark B",
            "/Type": "/Fit"
        },
        [
            {
                "/%is_open%": True,
                "/Page": writer.pages[0].indirect_reference,
                "/Title": "Nested entry",
                "/Type": "/Fit"
            }
        ]
    ]
    assert caplog.messages[0].startswith("Detected cycle in outline structure for {")


@pytest.mark.enable_socket
@pytest.mark.timeout(10)
def test_get_outline__cyclic_references__first_points_to_ancestor(caplog):
    url = "https://github.com/user-attachments/files/24859044/circular_outline.pdf"
    name = "circular_outline.pdf"
    writer = PdfWriter(clone_from=BytesIO(get_data_from_url(url=url, name=name)))

    # Make the first outline item its own child.
    bookmark_a = writer.get_object(5)
    bookmark_a[NameObject("/First")] = bookmark_a.indirect_reference

    assert [item["/Title"] for item in writer.outline] == ["Bookmark A", "Bookmark B"]
    assert len(caplog.messages) == 2
    assert all(
        message.startswith("Detected cycle in outline structure for {")
        for message in caplog.messages
    )


def test_xfa__decompression_limit():
    payload = b"A" * 100_0000
    compressed = FlateDecode.encode(payload, 9)

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)

    stream = EncodedStreamObject()
    stream._data = compressed
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    stream_reference = writer._add_object(stream)

    acro = DictionaryObject()
    acro[NameObject("/XFA")] = ArrayObject([TextStringObject("datasets"), stream_reference])
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(acro)

    data = BytesIO()
    writer.write(data)
    data.flush()

    reader = PdfReader(data)
    with mock.patch("pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH", 75_000), pytest.raises(
            expected_exception=LimitReachedError, match=r"^Limit reached while decompressing. 902 bytes remaining.$"
    ):
        _ = reader.xfa
