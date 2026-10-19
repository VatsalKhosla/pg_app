"""Write the API's OpenAPI schema without starting it: ``python -m app.openapi [OUTPUT]``.

``make gen-client`` writes it to packages/api-client/openapi.json, which the web app's typed client
is generated from, and ``make check-client`` fails when that file is out of date. The settings are
fixed placeholders that ignore the environment, so every machine writes the same schema; nothing
in the schema depends on them.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import Settings
from app.main import create_app

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class _SchemaSettings(Settings):
    """Built only from the values given: no environment variables, no .env file."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def openapi_schema() -> dict[str, Any]:
    settings = _SchemaSettings.model_validate(
        {
            "app_env": "local",
            "log_level": "WARNING",
            # Placeholders: building the schema opens no connections and signs nothing.
            "database_url": "postgresql+asyncpg://openapi@127.0.0.1:9/openapi",
            "redis_url": "redis://127.0.0.1:9/0",
            "secret_key": "placeholder-for-the-openapi-export-0000",
        }
    )
    return create_app(settings).openapi()


def render() -> str:
    return json.dumps(openapi_schema(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the API's OpenAPI schema as JSON.")
    parser.add_argument("output", nargs="?", type=Path, help="file to write (default: stdout)")
    args = parser.parse_args(argv)
    text = render()
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
