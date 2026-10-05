"""Audit writer: rows written in the same transaction as the change (FR-47 - FR-49).

Layering: router.py -> service.py -> domain logic -> repository.py -> PostgreSQL.
"""
