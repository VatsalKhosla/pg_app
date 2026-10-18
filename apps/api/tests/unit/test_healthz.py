import asyncio

import httpx

from app.main import create_app


def _get(path: str) -> httpx.Response:
    # httpx's in-process ASGI transport rather than Starlette's TestClient: Starlette 1.7 deprecates
    # httpx in its TestClient in favour of httpx2, which this project hasn't adopted yet.
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
            return await client.get(path)

    return asyncio.run(request())


def test_healthz_reports_ok() -> None:
    response = _get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_is_in_the_openapi_schema() -> None:
    # The web app reaches /healthz through the typed client generated from this schema (step 0.6).
    assert "/healthz" in create_app().openapi()["paths"]
