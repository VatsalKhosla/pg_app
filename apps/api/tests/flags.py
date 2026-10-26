"""Feature flags fixed for a test; every flag not named keeps its default (app.core.flags)."""

from app.core.flags import FLAGS, Flag


class FixedFlags:
    def __init__(self, **values: bool) -> None:
        self._values = {Flag(name): value for name, value in values.items()}

    async def is_enabled(self, flag: Flag) -> bool:
        value = self._values.get(flag, FLAGS[flag].default)
        assert isinstance(value, bool), f"{flag} is not an on/off flag"
        return value
