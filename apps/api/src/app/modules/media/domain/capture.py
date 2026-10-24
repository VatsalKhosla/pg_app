"""When a photo was taken, from its EXIF (read before the EXIF is stripped).

Phones write DateTimeOriginal as local time ("2027:06:12 10:30:05") and, often, the offset
from UTC beside it ("+05:30"). Without an offset, the time is taken as India's.
"""

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Final

INDIA: Final = timezone(timedelta(hours=5, minutes=30))
_STAMP: Final = re.compile(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")
_OFFSET: Final = re.compile(r"([+-])(\d{2}):(\d{2})")


def taken_at(stamp: str | None, offset: str | None, *, before: datetime) -> datetime | None:
    """The moment a photo was taken, in UTC, if its EXIF says and the answer is plausible: not
    after ``before`` (the upload) and not before 2000."""
    match = _STAMP.fullmatch((stamp or "").strip("\x00 "))
    if match is None:
        return None
    zone: tzinfo = INDIA
    if offset and (found := _OFFSET.fullmatch(offset.strip("\x00 "))):
        sign = -1 if found.group(1) == "-" else 1
        zone = timezone(sign * timedelta(hours=int(found.group(2)), minutes=int(found.group(3))))
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        moment = datetime(year, month, day, hour, minute, second, tzinfo=zone)
    except ValueError:
        return None
    moment = moment.astimezone(UTC)
    if moment > before or moment.year < 2000:
        return None
    return moment
