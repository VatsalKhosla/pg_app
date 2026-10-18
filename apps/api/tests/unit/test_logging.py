import json
import logging

import pytest
import structlog

from app.core.logging import configure_logging


def _last_line(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = capsys.readouterr().out.strip().splitlines()
    parsed: dict[str, object] = json.loads(lines[-1])
    return parsed


def test_json_lines_carry_the_request_id_and_mask_phone_numbers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", fmt="json")
    structlog.contextvars.bind_contextvars(request_id="0192f6d4-8e1c-7c3a")
    try:
        structlog.stdlib.get_logger("test").info("otp sent", phone="+919876543210")
    finally:
        structlog.contextvars.clear_contextvars()

    line = _last_line(capsys)
    assert line["event"] == "otp sent"
    assert line["level"] == "info"
    assert line["request_id"] == "0192f6d4-8e1c-7c3a"
    assert line["phone"] == "******3210"
    assert str(line["timestamp"]).endswith("Z")


def test_stdlib_loggers_share_the_format_and_masking(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", fmt="json")

    logging.getLogger("uvicorn.error").warning("could not reach 98765 43210")

    line = _last_line(capsys)
    assert line["logger"] == "uvicorn.error"
    assert line["event"] == "could not reach ******3210"


def test_tracebacks_are_masked_too(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", fmt="json")

    try:
        raise ValueError("no account for +919876543210")
    except ValueError:
        structlog.stdlib.get_logger("test").exception("lookup failed")

    output = capsys.readouterr().out
    assert "+919876543210" not in output
    assert "******3210" in output
