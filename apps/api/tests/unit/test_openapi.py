import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.main import create_app
from app.openapi import main, openapi_schema, render
from tests.conftest import build_settings

PROBLEM_REF = {"$ref": "#/components/schemas/ProblemDetail"}


def _operations(schema: dict[str, Any]) -> list[dict[str, Any]]:
    return [operation for path in schema["paths"].values() for operation in path.values()]


def test_operation_ids_are_unique_camel_case_tag_and_function_name() -> None:
    operations = _operations(openapi_schema())
    ids = [operation["operationId"] for operation in operations]

    assert "systemHealthz" in ids
    assert "systemReadyz" in ids
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z][A-Za-z0-9]*", operation_id) for operation_id in ids)


def test_every_operation_declares_its_errors_as_problem_details() -> None:
    for operation in _operations(openapi_schema()):
        responses = operation["responses"]
        for status in ("4XX", "5XX"):
            assert responses[status]["content"] == {
                "application/problem+json": {"schema": PROBLEM_REF}
            }, operation["operationId"]


def test_fastapis_validation_error_schema_is_replaced_by_problem_details() -> None:
    schemas = openapi_schema()["components"]["schemas"]

    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas
    assert set(schemas["ProblemDetail"]["required"]) == {"title", "status", "code"}
    assert "requestId" in schemas["ProblemDetail"]["properties"]


def test_validation_errors_fall_under_the_problem_details_for_4xx() -> None:
    app = create_app(build_settings())

    @app.get("/probe/{count}", tags=["probe"])
    async def probe(count: int) -> dict[str, int]:
        return {"count": count}

    schema = app.openapi()
    responses = schema["paths"]["/probe/{count}"]["get"]["responses"]

    # FastAPI adds no 422 of its own once 4XX is declared.
    assert "422" not in responses
    assert responses["4XX"]["content"] == {"application/problem+json": {"schema": PROBLEM_REF}}
    assert "HTTPValidationError" not in schema["components"]["schemas"]


def test_an_explicit_422_is_served_as_problem_details_too() -> None:
    app = create_app(build_settings())

    @app.post("/probe", tags=["probe"], responses={422: {"description": "Dates out of range"}})
    async def probe() -> dict[str, str]:
        return {}

    response = app.openapi()["paths"]["/probe"]["post"]["responses"]["422"]

    assert response["content"] == {"application/problem+json": {"schema": PROBLEM_REF}}


def test_documented_non_problem_errors_keep_their_own_body() -> None:
    readyz = openapi_schema()["paths"]["/readyz"]["get"]["responses"]

    assert readyz["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Readiness"
    }


def test_the_export_ignores_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = render()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "not a url")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    assert render() == baseline


def test_main_writes_the_schema_to_a_file(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"

    main([str(output)])

    text = output.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert json.loads(text)["info"]["title"].endswith(" API")


def test_main_writes_to_stdout_without_a_path(capsys: pytest.CaptureFixture[str]) -> None:
    main([])

    assert json.loads(capsys.readouterr().out)["openapi"].startswith("3.")
