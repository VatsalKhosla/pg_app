from collections.abc import Callable
from datetime import date
from typing import Annotated

import httpx
import pytest
from fastapi import FastAPI, Query
from pydantic import Field

from app.config import Settings
from app.core.errors import AppError
from app.core.schemas import ApiModel
from app.main import create_app

type Requester = Callable[..., httpx.Response]

PROBLEM_JSON = "application/problem+json"


class BedTakenError(AppError):
    status = 409
    code = "TEST_BED_TAKEN"
    title = "Bed already taken"


class Reservation(ApiModel):
    move_in: date
    stay_months: int = Field(ge=1)


@pytest.fixture
def app(make_settings: Callable[..., Settings]) -> FastAPI:
    app = create_app(make_settings())

    @app.get("/test/conflict")
    async def conflict() -> None:
        raise BedTakenError("Someone reserved this bed a moment ago.")

    @app.get("/test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    @app.post("/test/reservations")
    async def reserve(
        reservation: Reservation, limit: Annotated[int, Query(le=50)] = 10
    ) -> dict[str, int]:
        return {"stayMonths": reservation.stay_months, "limit": limit}

    return app


def test_unknown_routes_are_problem_documents_with_a_request_id(
    app: FastAPI, request_app: Requester
) -> None:
    response = request_app(app, "GET", "/no-such-route")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "code": "NOT_FOUND",
        "requestId": response.headers["x-request-id"],
    }


def test_wrong_methods_keep_the_allow_header(app: FastAPI, request_app: Requester) -> None:
    response = request_app(app, "DELETE", "/healthz")

    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]


def test_app_errors_carry_their_status_code_and_detail(
    app: FastAPI, request_app: Requester
) -> None:
    body = request_app(app, "GET", "/test/conflict").json()

    assert body["status"] == 409
    assert body["code"] == "TEST_BED_TAKEN"
    assert body["title"] == "Bed already taken"
    assert body["detail"] == "Someone reserved this bed a moment ago."


def test_validation_errors_point_at_each_field_without_echoing_input(
    app: FastAPI, request_app: Requester
) -> None:
    response = request_app(
        app,
        "POST",
        "/test/reservations",
        params={"limit": 500},
        json={"moveIn": "not-a-date-9876543210", "stayMonths": 0},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert {(error.get("pointer"), error.get("parameter")) for error in body["errors"]} == {
        ("/moveIn", None),
        ("/stayMonths", None),
        (None, "limit"),
    }
    assert all(error["code"] and error["detail"] for error in body["errors"])
    assert "not-a-date" not in response.text


def test_valid_camel_case_input_is_accepted(app: FastAPI, request_app: Requester) -> None:
    response = request_app(
        app, "POST", "/test/reservations", json={"moveIn": "2027-07-01", "stayMonths": 11}
    )

    assert response.status_code == 200
    assert response.json() == {"stayMonths": 11, "limit": 10}


def test_unknown_fields_are_rejected(app: FastAPI, request_app: Requester) -> None:
    response = request_app(
        app,
        "POST",
        "/test/reservations",
        json={"moveIn": "2027-07-01", "stayMonths": 11, "priceRupees": 1},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["pointer"] == "/priceRupees"


def test_unexpected_errors_hide_their_message(app: FastAPI, request_app: Requester) -> None:
    response = request_app(app, "GET", "/test/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text
    assert body["requestId"] == response.headers["x-request-id"]
