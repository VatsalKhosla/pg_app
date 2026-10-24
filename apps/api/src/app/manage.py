"""Operator commands: ``python -m app.manage --help``, or ``make manage args="staff list"``.

They run with the API's settings (``.env`` locally, the environment's variables when deployed) and
act on that environment's database directly, so only someone trusted with it can run them. Every
change is written to the audit log.

    staff add PHONE --role ROLE [--role ROLE ...] [--email ADDRESS] [--name NAME]
    staff remove PHONE [--role ROLE ...]
    staff list
    staff enrol-authenticator PHONE
    staff remove-authenticator PHONE
    staff remove-google PHONE
    geo load [--file PATH]
    media buckets

Making someone staff is the only way to staff sign-in: Google sign-in also needs their address
(``--email``), and the fallback needs an authenticator app (``enrol-authenticator``).

``geo load`` loads the geo reference data (cities, localities, campuses, metro lines and stations)
from app/modules/geo/data/places.json. It changes only what differs, so it is safe to run on every
deploy, and it is what ``make seed`` runs (ADR 0020).

``media buckets`` creates the object-storage buckets for local development (ADR 0022); when
deployed, Terraform does.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, TextIO

from app.config import Settings, get_settings
from app.core.actor import STAFF_ROLES, Role
from app.core.clock import Clock, SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.pagination import MAX_PAGE_SIZE, PageRequest
from app.modules.geo.reference import DATA_PATH, read_reference_data
from app.modules.geo.service import GeoReferenceLoader
from app.modules.identity.domain.phones import normalize_indian_mobile
from app.modules.identity.service import StaffAdmin, StaffAdminError, StaffDirectory
from app.modules.media.adapters.s3 import S3Storage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

# Codes from the app a new authenticator may be confirmed with before starting over.
CONFIRM_ATTEMPTS: Final = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.manage", description="Operator commands for this environment."
    )
    groups = parser.add_subparsers(dest="group", required=True)
    staff = groups.add_parser("staff", help="staff accounts and how they sign in").add_subparsers(
        dest="command", required=True
    )
    roles = sorted(STAFF_ROLES)

    add = staff.add_parser("add", help="make an account staff (creating it if needed)")
    add.add_argument("phone", help="an Indian mobile number")
    add.add_argument("--role", action="append", choices=roles, required=True)
    add.add_argument("--email", help="the Google account's address, for Google sign-in")
    add.add_argument("--name")

    remove = staff.add_parser("remove", help="take staff roles away (all unless --role is given)")
    remove.add_argument("phone")
    remove.add_argument("--role", action="append", choices=roles)

    staff.add_parser("list", help="list staff accounts")

    enrol = staff.add_parser(
        "enrol-authenticator", help="set up an authenticator app for the fallback sign-in"
    )
    enrol.add_argument("phone")

    drop = staff.add_parser("remove-authenticator", help="remove an authenticator app")
    drop.add_argument("phone")

    unlink = staff.add_parser(
        "remove-google", help="unlink a replaced Google account, so the next one links again"
    )
    unlink.add_argument("phone")

    geo = groups.add_parser("geo", help="the geo reference data").add_subparsers(
        dest="command", required=True
    )
    load = geo.add_parser("load", help="load the reference data (only what changed)")
    load.add_argument("--file", type=Path, default=DATA_PATH, help="default: %(default)s")

    media = groups.add_parser("media", help="object storage for uploads").add_subparsers(
        dest="command", required=True
    )
    media.add_parser("buckets", help="create the buckets (local development only)")
    return parser


def _phone(raw: str) -> str:
    phone = normalize_indian_mobile(raw)
    if phone is None:
        msg = "not an Indian mobile number"
        raise StaffAdminError(msg)
    return phone


def _grouped(secret: str) -> str:
    return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


class _Commands:
    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Clock,
        secret: bytes,
        out: TextIO,
        read_code: Callable[[], str],
    ) -> None:
        self._db = db
        self._admin = StaffAdmin(db, clock, secret=secret)
        self._out = out
        self._read_code = read_code

    def _say(self, line: str) -> None:
        self._out.write(line + "\n")

    async def run(self, args: argparse.Namespace) -> int:
        match args.command:
            case "add":
                roles = await self._admin.add(
                    _phone(args.phone),
                    frozenset(Role(role) for role in args.role),
                    email=None if args.email is None else args.email.strip(),
                    name=args.name,
                )
                self._say(f"Staff roles now: {', '.join(sorted(roles))}.")
            case "remove":
                left = await self._admin.remove(
                    _phone(args.phone),
                    None if args.role is None else frozenset(Role(role) for role in args.role),
                )
                self._say(
                    f"Staff roles left: {', '.join(sorted(left))}."
                    if left
                    else "No longer staff: staff sessions stopped and the authenticator removed."
                )
            case "list":
                await self._list()
            case "enrol-authenticator":
                return await self._enrol(_phone(args.phone))
            case "remove-authenticator":
                removed = await self._admin.remove_authenticator(_phone(args.phone))
                self._say("Authenticator removed." if removed else "No authenticator was set up.")
            case "remove-google":
                removed = await self._admin.remove_google(_phone(args.phone))
                self._say(
                    "Google account unlinked: the next Google sign-in links again."
                    if removed
                    else "No Google account was linked."
                )
            case _:  # pragma: no cover - argparse allows only the commands above
                return 2
        return 0

    async def _list(self) -> None:
        directory = StaffDirectory(self._db)
        cursor = None
        while True:
            records, cursor = await directory.page(PageRequest(after=cursor, limit=MAX_PAGE_SIZE))
            for record in records:
                user = record.user
                sign_in = [
                    *([f"Google ({record.google_email})"] if record.google_email else []),
                    *(["authenticator"] if record.authenticator else []),
                ]
                self._say(
                    f"{user.phone_e164}  {','.join(sorted(record.roles))}  "
                    f"{user.name or '-'}  {user.email or '-'}  "
                    f"signs in with: {', '.join(sign_in) or 'nothing yet'}"
                )
            if cursor is None:
                return

    async def _enrol(self, phone: str) -> int:
        enrolment = await self._admin.enrol_authenticator(phone)
        self._say("In the authenticator app, add an account with this setup key (time based):")
        self._say(f"    {_grouped(enrolment.secret)}")
        self._say("or open this link on the phone that has the app:")
        self._say(f"    {enrolment.uri}")
        self._say("Don't paste either into a website: anyone with them can make codes.")
        for _ in range(CONFIRM_ATTEMPTS):
            code = self._read_code().strip()
            if await self._admin.confirm_authenticator(phone, code):
                self._say("Authenticator set up: it signs in from now on.")
                return 0
            self._say("That code isn't right; try the next one the app shows.")
        self._say("Not confirmed. Run the command again to start over.")
        return 1


async def _load_geo(db: AsyncSession, *, clock: Clock, path: Path, out: TextIO) -> int:
    report = await GeoReferenceLoader(db, clock).load(read_reference_data(path))
    for kind in report.kinds:
        left = f", {kind.not_listed} no longer listed (left alone)" if kind.not_listed else ""
        out.write(
            f"{kind.kind.replace('_', ' ')}: {kind.rows} ({kind.inserted} new, "
            f"{kind.updated} changed{left})\n"
        )
    out.write(
        f"Geo reference data loaded ({report.digest[:12]})."
        if report.changed
        else "Geo reference data already up to date."
    )
    out.write("\n")
    return 0


async def _main(
    args: argparse.Namespace,
    *,
    settings: Settings,
    clock: Clock,
    out: TextIO,
    read_code: Callable[[], str],
) -> int:
    engine = create_engine(settings, application_name=f"{settings.otel_service_name}-manage")
    try:
        async with create_sessionmaker(engine)() as db:
            if args.group == "geo":
                return await _load_geo(db, clock=clock, path=args.file, out=out)
            commands = _Commands(
                db,
                clock=clock,
                secret=settings.secret_key.get_secret_value().encode(),
                out=out,
                read_code=read_code,
            )
            return await commands.run(args)
    except StaffAdminError as error:
        out.write(f"Not done: {error}.\n")
        return 1
    finally:
        await engine.dispose()


def _media_buckets(settings: Settings, out: TextIO) -> int:
    if settings.is_deployed:
        out.write("Not done: deployed environments get their buckets from Terraform.\n")
        return 1
    created = S3Storage.from_settings(settings).ensure_local_buckets(
        private=settings.media_private_bucket,
        public=settings.media_public_bucket,
        web_origin=settings.site_url,
    )
    out.write(
        f"Buckets ready ({', '.join(created)} created)."
        if created
        else "Buckets ready (both existed)."
    )
    out.write("\n")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    clock: Clock | None = None,
    out: TextIO = sys.stdout,
    read_code: Callable[[], str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.group == "media":
        return _media_buckets(settings or get_settings(), out)
    return asyncio.run(
        _main(
            args,
            settings=settings or get_settings(),
            clock=clock or SystemClock(),
            out=out,
            read_code=read_code or (lambda: input("Code from the app: ")),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
