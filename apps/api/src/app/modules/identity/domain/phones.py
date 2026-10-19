"""Phone numbers as accounts know them: Indian mobile numbers in E.164 (ARCHITECTURE §12).

Sign-in codes go out by SMS through a DLT-registered Indian sender, which reaches only Indian
mobile numbers, so those are the only numbers an account can have for now. People type them in
many ways ("98765 43210", "+91-98765-43210", "098765 43210"); all become "+919876543210".
"""

import re
from typing import Final

_SEPARATORS: Final = re.compile(r"[\s().-]")
# Indian mobile numbers: ten digits, the first 6 to 9. ASCII digits only.
_MOBILE: Final = re.compile(r"[6-9][0-9]{9}")


def normalize_indian_mobile(raw: str) -> str | None:
    """The E.164 form of an Indian mobile number, or None if ``raw`` isn't one."""
    number = _SEPARATORS.sub("", raw)
    if number.startswith("+91"):
        number = number[3:]
    elif number.startswith("0091"):
        number = number[4:]
    elif len(number) == 12 and number.startswith("91"):
        number = number[2:]
    elif len(number) == 11 and number.startswith("0"):
        number = number[1:]
    return f"+91{number}" if _MOBILE.fullmatch(number) else None
