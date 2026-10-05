"""Mounts every module router under /api/v1 (SADD 2.6).

Add endpoints in the module's own router.py; this file only needs to change
when a new module is added.
"""

from fastapi import APIRouter

from app.modules.audit.router import router as audit_router
from app.modules.catalogue.router import router as catalogue_router
from app.modules.identity.router import router as identity_router
from app.modules.inventory.router import router as inventory_router
from app.modules.ordering.router import router as ordering_router
from app.modules.payments.router import router as payments_router
from app.modules.pricing.router import router as pricing_router
from app.modules.slots.router import router as slots_router

api_router = APIRouter(prefix="/api/v1")
for module_router in (
    identity_router,
    catalogue_router,
    inventory_router,
    slots_router,
    pricing_router,
    ordering_router,
    payments_router,
    audit_router,
):
    api_router.include_router(module_router)
