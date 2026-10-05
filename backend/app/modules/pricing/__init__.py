"""Pure pricing engine and price quotes (FR-22 - FR-26). No database access in the engine.

Layering: router.py -> service.py -> domain logic -> repository.py -> PostgreSQL.
"""
