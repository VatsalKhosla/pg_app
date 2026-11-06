"""The top requests' queries, explained (step 8.2): `python -m tests.load.explain OUT_DIR`, with
DATABASE_URL naming the load tests' database (scripts/load-test.sh leaves it seeded).

It drives the API in-process, as the browser would: search near a campus, in a locality and by
name, the map's pins, a PG's page, a quote and a hold. It records every statement each request
runs, then runs EXPLAIN (ANALYZE, BUFFERS) on each read inside a transaction that is rolled back.
Writes ran once already, and would only collide with themselves, so they get the planner's plan
alone. A request's slowest statements lead its section in OUT_DIR/query-plans.txt, and
OUT_DIR/query-plans.json sums them up.
"""

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import event

from app.config import Settings
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.main import create_app

PHONE = "+919900000001"
WRITES = ("INSERT", "UPDATE", "DELETE")


@dataclass
class Captured:
    request: str
    statements: list[tuple[str, Any]] = field(default_factory=list)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    report, summary = asyncio.run(_explained())
    (out / "query-plans.txt").write_text(report)
    (out / "query-plans.json").write_text(json.dumps(summary, indent=2) + "\n")
    for row in summary:
        print(json.dumps(row))  # noqa: T201 - the tool's output


async def _explained() -> tuple[str, list[dict[str, Any]]]:
    app = create_app(Settings())
    captured: list[Captured] = []

    def capture(_conn: Any, _cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        # Plain statements only: EXPLAIN takes neither SET and the like, nor a batch of rows.
        plain = statement.lstrip().upper().startswith(("SELECT", "WITH", *WRITES))
        if captured and plain and not isinstance(parameters, list):
            captured[-1].statements.append((statement, parameters))

    async with app.router.lifespan_context(app):
        await app.state.redis.flushdb()  # every answer from the database, none from the cache
        event.listen(app.state.engine.sync_engine, "before_cursor_execute", capture)
        try:
            await _drive(app, captured)
        finally:
            event.remove(app.state.engine.sync_engine, "before_cursor_execute", capture)
        timed = [each for each in captured if each.request != "signing in"]
        return await _explain(app, timed)


async def _drive(app: FastAPI, captured: list[Captured]) -> None:
    """The requests, each recorded under its own name."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        campus = (await client.get("/v1/campuses")).json()["items"][0]["slug"]
        locality = (await client.get("/v1/localities")).json()["items"][0]["slug"]
        found = await client.get("/v1/search/properties", params={"q": "fictional sample"})
        slug = found.json()["items"][0]["slug"]
        room = (await client.get(f"/v1/properties/{slug}")).json()["categories"][0]["id"]
        reads = {
            "search near a campus": ("/v1/search/properties", {"campus": campus}),
            "search in a locality": ("/v1/search/properties", {"locality": locality}),
            "search by name": ("/v1/search/properties", {"q": "royal residency"}),
            "the map's pins": ("/v1/map/pins", {"bbox": "77.15,28.64,77.25,28.72", "zoom": 13}),
            "a PG's page": (f"/v1/properties/{slug}", {}),
        }
        for name, (path, params) in reads.items():
            captured.append(Captured(name))
            answer = await client.get(path, params=params)
            assert answer.status_code == 200, (name, answer.text)
        captured.append(Captured("signing in"))  # set aside: not one of the requests timed
        await _sign_in(client)
        csrf = {CSRF_HEADER: client.cookies[CSRF_COOKIE]}
        move_in = (app.state.clock.now() + timedelta(days=30)).date().isoformat()
        captured.append(Captured("a quote"))
        quote = await client.post(
            "/v1/quotes",
            json={"roomCategory": room, "moveIn": move_in, "stayMonths": 11},
            headers=csrf,
        )
        assert quote.status_code == 201, quote.text
        captured.append(Captured("a hold"))
        held = await client.post(
            "/v1/bookings",
            json={"quote": quote.json()["id"]},
            headers={**csrf, "Idempotency-Key": f"explain-{uuid.uuid4().hex}"},
        )
        assert held.status_code in {201, 409}, held.text


async def _explain(app: FastAPI, captured: list[Captured]) -> tuple[str, list[dict[str, Any]]]:
    """Each request's statements explained, slowest first, and a summary of them."""
    report: list[str] = []
    summary: list[dict[str, Any]] = []
    for request in captured:
        explained = []
        for statement, parameters in request.statements:
            write = statement.lstrip().upper().startswith(WRITES)
            options = "" if write else "(ANALYZE, BUFFERS) "
            async with app.state.engine.connect() as connection:
                transaction = await connection.begin()
                result = await connection.exec_driver_sql(
                    f"EXPLAIN {options}{statement}", parameters
                )
                plan = [row[0] for row in result]
                await transaction.rollback()
            took = 0.0 if write else float(plan[-1].rsplit(":", 1)[1].split()[0])
            explained.append((took, statement, plan))
        explained.sort(key=lambda item: item[0], reverse=True)
        total = round(sum(item[0] for item in explained), 2)
        scans = {
            line.split("Seq Scan on ")[1].split()[0]
            for _, _, plan in explained
            for line in plan
            if "Seq Scan on " in line
        }
        summary.append(
            {
                "request": request.request,
                "statements": len(explained),
                "databaseMs": total,
                "slowestMs": explained[0][0] if explained else 0,
                "seqScans": sorted(scans),
            }
        )
        report.append(f"== {request.request}: {len(explained)} statements, {total} ms\n")
        for took, statement, plan in explained[:3]:
            report.append(f"\n-- {took} ms\n{statement.strip()}\n\n" + "\n".join(plan) + "\n")
        report.append("\n")
    return "".join(report), summary


async def _sign_in(client: httpx.AsyncClient) -> None:
    """A fictional student, signed in with the code a local API hands back."""
    await client.get("/v1/auth/csrf")
    csrf = {CSRF_HEADER: client.cookies[CSRF_COOKIE]}
    asked = await client.post(
        "/v1/auth/otp/request", json={"phone": PHONE, "humanCheckToken": "explain"}, headers=csrf
    )
    notice = (await client.get("/v1/privacy-notice")).json()
    challenge = asked.json()
    signed_in = await client.post(
        "/v1/auth/otp/verify",
        json={
            "challengeId": challenge["challengeId"],
            "code": challenge["developmentCode"],
            "consent": {"noticeVersion": notice["version"], "purposes": ["account"]},
        },
        headers=csrf,
    )
    assert signed_in.status_code == 200, signed_in.text


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "test-results/load"))
