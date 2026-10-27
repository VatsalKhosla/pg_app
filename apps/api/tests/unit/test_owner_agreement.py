"""The owner agreement's rules and texts (step 2.6, ADR 0025), without a database."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from app.config import BRAND_NAME, Settings
from app.main import create_app
from app.modules.catalog.agreements import AGREEMENTS_DIR, FileAgreements
from app.modules.catalog.domain.agreements import VERSION_PATTERN, Agreement, needs_acceptance


def test_an_acceptance_names_the_hash_of_exactly_the_text_shown() -> None:
    agreement = Agreement("draft-1", "You pay a placement fee.")

    assert agreement.sha256 == hashlib.sha256(b"You pay a placement fee.").hexdigest()
    assert Agreement("draft-1", "You pay a placement fee!").sha256 != agreement.sha256


@pytest.mark.parametrize(
    ("accepted", "current", "needed"),
    [(None, "draft-1", True), ("draft-1", "draft-1", False), ("draft-1", "draft-2", True)],
)
def test_owners_accept_again_whenever_a_new_version_is_current(
    accepted: str | None, current: str, needed: bool
) -> None:
    assert needs_acceptance(accepted, current) is needed


def test_the_agreement_in_use_is_a_draft_that_says_so_and_names_the_brand() -> None:
    agreement = FileAgreements().get(Settings.model_fields["owner_agreement_version"].default)

    assert agreement is not None
    assert agreement.text.startswith(f"# {BRAND_NAME} owner agreement")
    assert "DRAFT" in agreement.text.splitlines()[2]
    assert "{brand}" not in agreement.text


def test_every_version_on_file_has_a_name_owners_can_be_asked_to_accept() -> None:
    versions = [path.stem for path in AGREEMENTS_DIR.glob("*.md")]

    assert versions
    assert all(VERSION_PATTERN.fullmatch(version) for version in versions)


@pytest.mark.parametrize("version", ["draft-0", "../agreements/draft-1", "Draft-1", ""])
def test_a_version_without_its_own_file_has_no_text(version: str) -> None:
    assert FileAgreements().get(version) is None


def test_the_brand_is_filled_in_as_the_text_is_read(tmp_path: Path) -> None:
    (tmp_path / "v1.md").write_text("# {brand} owner agreement\n\nAgreed with {brand}.\n")

    agreement = FileAgreements(tmp_path, brand="Fictional Beds").get("v1")

    assert agreement == Agreement(
        "v1", "# Fictional Beds owner agreement\n\nAgreed with Fictional Beds.\n"
    )


def test_the_api_wont_start_without_the_current_agreements_text(
    make_settings: Callable[..., Settings],
) -> None:
    with pytest.raises(RuntimeError, match="OWNER_AGREEMENT_VERSION draft-9 has no agreement text"):
        create_app(make_settings(owner_agreement_version="draft-9"))
