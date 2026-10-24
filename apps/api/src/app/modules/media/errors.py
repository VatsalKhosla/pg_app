"""Errors of the media module, as problem details with stable codes (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class MediaNotAllowedError(AppError):
    """A file of a type, or a size, that this kind of upload doesn't take."""

    status = 422
    code = "MEDIA_NOT_ALLOWED"
    title = "That file can't be uploaded here"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class MediaNotUploadedError(AppError):
    """Asked to process an upload that storage doesn't have yet."""

    status = 409
    code = "MEDIA_NOT_UPLOADED"
    title = "The file hasn't been uploaded yet"
