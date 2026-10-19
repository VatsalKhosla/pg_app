"""What people tell us about themselves (ARCHITECTURE §6): the least the service needs.

A name to address them by; where they study or work, which helps find PGs near it; and, if they
choose to say, their gender, used only to show PGs they can stay in (girls', boys' or co-living).
"""

from enum import StrEnum
from typing import Final

NAME_MAX_LENGTH: Final = 80
PLACE_MAX_LENGTH: Final = 120


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
