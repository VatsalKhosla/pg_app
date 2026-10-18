"""Migration hygiene without a database: one linear history, and every migration reversible."""

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[2]


def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(API_ROOT / "alembic.ini")))


def test_there_is_a_single_head() -> None:
    assert len(_scripts().get_heads()) == 1


def test_every_migration_implements_downgrade() -> None:
    for revision in _scripts().walk_revisions():
        assert revision.path is not None
        tree = ast.parse(Path(revision.path).read_text())
        downgrade = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
        )
        statements = [
            node
            for node in downgrade.body
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        ]
        assert statements, f"{revision.path}: downgrade() has no body"
        assert not all(isinstance(node, ast.Pass) for node in statements), (
            f"{revision.path}: downgrade() only passes"
        )
