"""Place, modify and cancel orders; state machine; resource allocator; idempotency (FR-27 - FR-40).

Layering: router.py -> service.py -> domain logic -> repository.py -> PostgreSQL.
"""
