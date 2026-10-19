import re

from app.main import create_app
from tests.authorization import CALLERS, MATRIX, PATH_VALUES, api_routes
from tests.conftest import build_settings

ROUTES = api_routes(create_app(build_settings()))


def test_every_route_has_an_entry_in_the_authorization_matrix() -> None:
    missing = sorted(ROUTES - MATRIX.keys())

    assert missing == [], f"say who may call these in tests/authorization.py: {missing}"


def test_every_entry_in_the_matrix_is_a_route() -> None:
    assert sorted(MATRIX.keys() - ROUTES) == []


def test_every_entry_says_what_each_caller_gets() -> None:
    incomplete = [route for route, rule in MATRIX.items() if set(rule.expected) != set(CALLERS)]

    assert incomplete == []


def test_every_path_parameter_says_what_fills_it() -> None:
    unfilled = [
        (method, path)
        for (method, path), rule in MATRIX.items()
        if set(re.findall(r"\{([^}]+)\}", path)) != set(rule.path)
        or not set(rule.path.values()) <= PATH_VALUES
    ]

    assert unfilled == []
