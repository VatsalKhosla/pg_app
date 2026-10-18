"""Business modules: identity, geo, catalog, pricing, booking, payments, ledger and the rest.

Each module has a pure ``domain/`` package plus ``service.py``, ``repository.py``, ``router.py``,
``schemas.py``, ``models.py`` and ``policies.py``. Modules talk to each other only through
services or outbox events, never through each other's tables.
"""
