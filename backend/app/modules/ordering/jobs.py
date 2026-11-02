"""The ordering module's caf-worker jobs."""

from app.core import clock as clock
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.modules.ordering.auto_prep import AutoPrepService
from app.modules.ordering.outbox import OutboxDeliverer
from app.modules.ordering.sweeper import HoldSweeper
from app.modules.payments.gateway import TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import MockpayGateway, get_mockpay_client
from app.worker.jobs import Job

# How often auto-prep checks for due slots; an order moves at most this late.
AUTO_PREP_CHECK_S = 30
# How often unacknowledged voids and refunds are sent again (FR-39).
OUTBOX_RETRY_S = 10


def auto_start_preparation() -> None:
    with get_sessionmaker()() as session:
        AutoPrepService(session).start_due(clock.now())


def sweep_expired_holds() -> None:
    with get_sessionmaker()() as session:
        HoldSweeper(session, get_settings().hold_expiry_s).sweep(clock.now())


def deliver_payment_outbox() -> None:
    with get_sessionmaker()() as session:
        gateway = TransactionGuardedGateway(MockpayGateway(get_mockpay_client()), session)
        OutboxDeliverer(session, gateway).deliver()


ORDERING_JOBS = [
    Job("auto-prep", auto_start_preparation, AUTO_PREP_CHECK_S),
    # FR-34: also at start-up, so holds left by a crash are recovered at once (NFR-15).
    Job(
        "hold-sweeper",
        sweep_expired_holds,
        get_settings().sweep_interval_s,
        run_at_startup=True,
    ),
    Job("payment-outbox", deliver_payment_outbox, OUTBOX_RETRY_S),
]
