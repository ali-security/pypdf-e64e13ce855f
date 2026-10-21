"""Test the pypdf.generic._base module."""
from io import BytesIO

import pytest

from pypdf.errors import LimitReachedError
from pypdf.generic import FloatObject, NameObject, NumberObject


def test_number_object__read_from_stream__limits() -> None:
    stream = BytesIO(b"13.37\n")
    assert NumberObject.read_from_stream(stream) == FloatObject("13.37")

    stream = BytesIO(f"{'1' * 100}\n".encode())
    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Read stream length of 101 exceeds maximum allowed length of 64\.$"
    ):
        NumberObject.read_from_stream(stream)


def test_name_object__read_from_stream__limits() -> None:
    stream = BytesIO(b"/My#20Name\n")
    assert NameObject.read_from_stream(stream, pdf=None) == NameObject("/My Name")

    stream = BytesIO(f"/{'SomeName' * 5000}\n".encode())
    with pytest.raises(
            expected_exception=LimitReachedError,
            match=r"^Read stream length of 8176 exceeds maximum allowed length of 4096\.$"
    ):
        NameObject.read_from_stream(stream, pdf=None)
