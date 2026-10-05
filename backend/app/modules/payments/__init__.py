"""Payment gateway adapter over mockpay (FR-33, FR-41).

Never called inside an open database transaction (NFR-6).

Layering: router.py -> service.py -> domain logic -> repository.py -> PostgreSQL.
"""
