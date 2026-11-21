"""Errors that carry a message written for the reader, not the developer."""

from __future__ import annotations


class ConversionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def password_protected() -> ConversionError:
    return ConversionError(
        "password",
        "This PDF is password-protected. Open it in a PDF reader you trust, save an "
        "unprotected copy if you have the right to, and import that copy instead.",
    )


def extraction_forbidden() -> ConversionError:
    return ConversionError(
        "restricted",
        "This PDF's author has turned off text extraction. Proseway respects that "
        "setting and won't convert it.",
    )


def not_a_pdf() -> ConversionError:
    return ConversionError(
        "not_pdf",
        "This file doesn't look like a PDF. Check that it opens in a PDF reader.",
    )


def corrupt(detail: str = "") -> ConversionError:
    msg = "This PDF seems to be damaged and couldn't be read."
    if detail:
        msg += f" ({detail})"
    return ConversionError("corrupt", msg)


def empty() -> ConversionError:
    return ConversionError("empty", "This PDF has no pages.")
