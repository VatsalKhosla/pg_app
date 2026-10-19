"""The OpenAPI schema, which the web app's typed client is generated from (``make gen-client``).

Two changes to FastAPI's defaults make the schema describe what the API really does:

- Operation ids are the route's first tag and function name in camelCase (``systemHealthz``)
  instead of ``healthz_healthz_get``, so generated names and schema diffs read well.
- Every operation declares its errors as RFC 9457 problem details (``application/problem+json``
  with ``ProblemDetail``), which ``install_error_handlers`` sends, instead of FastAPI's
  ``HTTPValidationError`` for 422.
"""

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from pydantic.alias_generators import to_camel

from app.core.errors import PROBLEM_JSON, ProblemDetail

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

# Added to every route. FastAPI files them under application/json; the schema is corrected below.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    "4XX": {"model": ProblemDetail, "description": "Client error (RFC 9457 problem details)"},
    "5XX": {"model": ProblemDetail, "description": "Server error (RFC 9457 problem details)"},
}

_ERROR_STATUSES = frozenset({"4XX", "5XX", "422"})
# FastAPI's validation error schemas, unused once 422 points at ProblemDetail.
_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def operation_id(route: APIRoute) -> str:
    """The route's first tag and function name in camelCase: ``systemHealthz``."""
    prefix = f"{route.tags[0]}_" if route.tags else ""
    return to_camel(f"{prefix}{route.name}")


def _with_problem_errors(schema: dict[str, Any]) -> dict[str, Any]:
    """Declare error responses as problem+json. Idempotent, since FastAPI caches the schema."""
    problem = {PROBLEM_JSON: {"schema": {"$ref": "#/components/schemas/ProblemDetail"}}}
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            for status, response in operation.get("responses", {}).items():
                if status in _ERROR_STATUSES:
                    response["content"] = problem
                if status == "422":
                    response["description"] = "Invalid request (problem details with field errors)"
    components = schema.get("components", {}).get("schemas", {})
    for name in _FASTAPI_VALIDATION_SCHEMAS:
        components.pop(name, None)
    return schema


class Api(FastAPI):
    """FastAPI with the schema adjustments above."""

    def openapi(self) -> dict[str, Any]:
        return _with_problem_errors(super().openapi())
