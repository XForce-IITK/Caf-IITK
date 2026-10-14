"""US-40 (CAFIITK-165; FR-53 - FR-57) acceptance tests TC-US40-AC1..AC6 via
GET /api/v1/admin/proposals and POST /api/v1/admin/proposals/{id}/approve|reject.

Proposals are inserted directly, as the agent run (CAFIITK-164) stores them: the
payload follows `app.modules.proposals.payloads`, and expiry is the target slot's
start (prep priority) or the service window's start (disable, replenishment).
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.security import create_access_token
from app.models.agent import AgentRun, Proposal
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    AgentRunStatus,
    AgentSource,
    AgentTrigger,
    ItemCategory,
    ItemStatus,
    OrderStatus,
    ProposalStatus,
    ProposalType,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderTransition
from app.models.platform import AuditLog
from app.modules.proposals.jobs import PROPOSAL_JOBS, expire_proposals
from app.modules.proposals.service import ProposalNotPendingError, ProposalService
from app.worker.jobs import all_jobs

PROPOSALS = "/api/v1/admin/proposals"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
WINDOW_START = datetime(2026, 10, 6, 12, 0, tzinfo=IST)
# Before service: every proposal below is still decidable.
NOW = datetime(2026, 10, 6, 10, 0, tzinfo=IST)


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(engine: Engine, role: Role) -> User:
    user = User(
        id=uuid.uuid4(),
        name=f"{role.value} user",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def api(db_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return db_client


@pytest.fixture
def admin(engine: Engine) -> User:
    return _user(engine, Role.ADMIN)


@pytest.fixture
def menu(engine: Engine, admin: User) -> dict[str, Any]:
    """Thali (100 portions set) and Dosa (none set), a service day, two slots and a run."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    dosa = MenuItem(id=uuid.uuid4(), name="Dosa", category=ItemCategory.MEAL, price_paise=5000)
    day = ServiceDay(
        service_date=DAY,
        window_start=time(12, 0),
        window_end=time(14, 0),
        slot_len_min=15,
        default_capacity=30,
    )
    slots = [
        Slot(
            id=uuid.uuid4(),
            service_date=DAY,
            starts_at=WINDOW_START + timedelta(minutes=minutes),
            ends_at=WINDOW_START + timedelta(minutes=minutes + 15),
            capacity=30,
        )
        for minutes in (0, 15)
    ]
    # Requested by the admin, so the db_client clean-up's TRUNCATE users cascades to it.
    run = AgentRun(
        id=uuid.uuid4(),
        trigger=AgentTrigger.ON_DEMAND,
        requested_by=admin.id,
        status=AgentRunStatus.SUCCEEDED,
        source=AgentSource.LLM,
    )
    _add(engine, thali, dosa, day, run)
    _add(engine, *slots, DailyInventory(item_id=thali.id, service_date=DAY, total=100))
    return {"thali": thali, "dosa": dosa, "slots": slots, "run": run}


def _propose(
    engine: Engine,
    menu: dict[str, Any],
    proposal_type: ProposalType,
    payload: dict[str, Any],
    *,
    slot: Slot | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    proposal = Proposal(
        id=uuid.uuid4(),
        run_id=menu["run"].id,
        type=proposal_type,
        target_date=DAY,
        target_slot_id=slot.id if slot else None,
        payload=payload,
        rationale="Forecast shows a stock-out by 13:00",
        source=AgentSource.LLM,
        expires_at=slot.starts_at if slot else WINDOW_START,
        created_at=created_at or NOW - timedelta(minutes=30),
    )
    _add(engine, proposal)
    return proposal.id


def _replenish(engine: Engine, menu: dict[str, Any], *lines: tuple[MenuItem, int]) -> uuid.UUID:
    payload = {
        "lines": [{"item_id": str(item.id), "additional_portions": qty} for item, qty in lines]
    }
    return _propose(engine, menu, ProposalType.REPLENISH, payload)


def _approve(api: TestClient, proposal_id: uuid.UUID, admin: User) -> Any:
    return api.post(f"{PROPOSALS}/{proposal_id}/approve", headers=_auth(admin))


def _reject(api: TestClient, proposal_id: uuid.UUID, admin: User, body: Any) -> Any:
    return api.post(f"{PROPOSALS}/{proposal_id}/reject", headers=_auth(admin), json=body)


def _proposal(engine: Engine, proposal_id: uuid.UUID) -> Proposal:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        assert proposal is not None
        return proposal


def _total(engine: Engine, item: MenuItem) -> int | None:
    with Session(engine) as session:
        row = session.get(DailyInventory, (item.id, DAY))
        return None if row is None else row.total


def _audit(engine: Engine, proposal_id: uuid.UUID) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.correlation_id == str(proposal_id))
                .order_by(AuditLog.id)
            )
        )


def test_tc_us40_ac1_approved_replenishment_adds_portions_under_admin_identity(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPROVED"
    assert _total(engine, menu["thali"]) == 140
    proposal = _proposal(engine, proposal_id)
    assert proposal.status is ProposalStatus.APPROVED
    assert proposal.decided_by == admin.id
    assert proposal.decided_at == NOW
    change, decision = _audit(engine, proposal_id)
    assert change.action == "INVENTORY_REPLENISHED"
    assert change.actor_id == str(admin.id)
    assert change.actor_role == "ADMIN"
    assert change.before == {"total": 100, "allocated": 0}
    assert change.after == {"total": 140, "allocated": 0, "proposal_id": str(proposal_id)}
    assert decision.action == "PROPOSAL_APPROVED"
    assert decision.actor_id == str(admin.id)


def test_replenishing_an_item_with_no_portions_set_creates_its_inventory(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 10), (menu["dosa"], 25))

    assert _approve(api, proposal_id, admin).status_code == 200

    assert _total(engine, menu["thali"]) == 110
    assert _total(engine, menu["dosa"]) == 25


@pytest.mark.parametrize("body", [None, {}, {"reason": ""}, {"reason": "   "}])
def test_tc_us40_ac2_reject_without_a_reason_is_422(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any], body: Any
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))

    assert _reject(api, proposal_id, admin, body).status_code == 422

    assert _proposal(engine, proposal_id).status is ProposalStatus.PENDING


def test_tc_us40_ac2_reject_with_a_reason_changes_nothing(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))

    response = _reject(api, proposal_id, admin, {"reason": "Kitchen is short-staffed"})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"
    assert response.json()["decision_reason"] == "Kitchen is short-staffed"
    assert _total(engine, menu["thali"]) == 100
    proposal = _proposal(engine, proposal_id)
    assert proposal.status is ProposalStatus.REJECTED
    assert proposal.decided_by == admin.id
    assert [row.action for row in _audit(engine, proposal_id)] == ["PROPOSAL_REJECTED"]
    # A decided proposal cannot be decided again.
    again = _approve(api, proposal_id, admin)
    assert again.status_code == 409
    assert again.json()["detail"]["proposal"]["status"] == "REJECTED"
    assert _total(engine, menu["thali"]) == 100


def test_tc_us40_ac3_item_removed_after_drafting_invalidates(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40), (menu["dosa"], 10))
    with Session(engine) as session, session.begin():
        dosa = session.get(MenuItem, menu["dosa"].id)
        assert dosa is not None
        dosa.status = ItemStatus.REMOVED

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 409
    proposal_out = response.json()["detail"]["proposal"]
    assert proposal_out["status"] == "INVALIDATED"
    assert str(menu["dosa"].id) in proposal_out["decision_reason"]
    assert _total(engine, menu["thali"]) == 100
    assert _total(engine, menu["dosa"]) is None
    assert _proposal(engine, proposal_id).status is ProposalStatus.INVALIDATED
    assert [row.action for row in _audit(engine, proposal_id)] == ["PROPOSAL_INVALIDATED"]


def test_a_partly_applied_change_that_breaks_a_bound_is_rolled_back(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    """Lines are applied in item order; a later line over 500 portions undoes the earlier."""
    first, second = sorted((menu["thali"], menu["dosa"]), key=lambda item: item.id)
    _add(engine, DailyInventory(item_id=menu["dosa"].id, service_date=DAY, total=100))
    with Session(engine) as session, session.begin():
        row = session.get(DailyInventory, (second.id, DAY))
        assert row is not None
        row.total = 450
    proposal_id = _replenish(engine, menu, (first, 10), (second, 100))

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 409
    assert response.json()["detail"]["proposal"]["status"] == "INVALIDATED"
    assert _total(engine, first) == 100
    assert _total(engine, second) == 450


def test_replenishment_above_p_repl_max_is_invalidated(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 201))

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 409
    assert "P-REPL_MAX" in response.json()["detail"]["proposal"]["decision_reason"]
    assert _total(engine, menu["thali"]) == 100


def test_tc_us40_ac4_proposal_past_its_target_start_expires(
    api: TestClient,
    engine: Engine,
    admin: User,
    menu: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))
    monkeypatch.setattr(clock, "now", lambda: WINDOW_START)

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 409
    assert response.json()["detail"]["proposal"]["status"] == "EXPIRED"
    assert _proposal(engine, proposal_id).status is ProposalStatus.EXPIRED
    assert _total(engine, menu["thali"]) == 100
    rejected = _reject(api, proposal_id, admin, {"reason": "Too late"})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["proposal"]["status"] == "EXPIRED"


def test_a_superseded_proposal_expires(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    older = _replenish(engine, menu, (menu["thali"], 40))
    newer = _propose(
        engine,
        menu,
        ProposalType.REPLENISH,
        {"lines": [{"item_id": str(menu["thali"].id), "additional_portions": 20}]},
        created_at=NOW - timedelta(minutes=5),
    )
    # A disable for another item is a different target and supersedes nothing.
    other = _propose(
        engine,
        menu,
        ProposalType.DISABLE,
        {"item_id": str(menu["dosa"].id), "reason": "Out of batter"},
        created_at=NOW - timedelta(minutes=1),
    )

    response = _approve(api, older, admin)

    assert response.status_code == 409
    assert response.json()["detail"]["proposal"]["status"] == "EXPIRED"
    assert _approve(api, newer, admin).status_code == 200
    assert _total(engine, menu["thali"]) == 120
    assert _proposal(engine, other).status is ProposalStatus.PENDING


def test_tc_us40_ac5_approved_disable_flags_the_item_until_the_end_of_the_day(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    thali = menu["thali"]
    proposal_id = _propose(
        engine, menu, ProposalType.DISABLE, {"item_id": str(thali.id), "reason": "Will run out"}
    )

    assert _approve(api, proposal_id, admin).status_code == 200

    with Session(engine) as session:
        item = session.get(MenuItem, thali.id)
        assert item is not None
        assert item.unavailable
        assert item.unavailable_reason == "Will run out"
        assert item.unavailable_source == str(proposal_id)
        assert item.unavailable_until == datetime(2026, 10, 7, 0, 0, tzinfo=IST)
    menu_out = api.get("/api/v1/menu", headers=_auth(admin)).json()
    [shown] = [i for i in menu_out["items"] if i["id"] == str(thali.id)]
    assert shown["not_orderable_reason"] == "UNAVAILABLE"
    assert shown["available_portions"] == 100
    change, _ = _audit(engine, proposal_id)
    assert change.action == "ITEM_FLAGGED"
    assert change.actor_id == str(admin.id)


def test_tc_us40_ac6_approved_prep_priority_orders_the_kitchen_queue(
    api: TestClient,
    engine: Engine,
    admin: User,
    menu: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thali, dosa = menu["thali"], menu["dosa"]
    current, nxt = menu["slots"]
    student = _user(engine, Role.STUDENT)
    for slot in (current, nxt):
        order = Order(
            id=uuid.uuid4(), student_id=student.id, slot_id=slot.id, status=OrderStatus.ACCEPTED
        )
        _add(engine, order)
        _add(
            engine,
            OrderLine(order_id=order.id, item_id=thali.id, qty=3),
            OrderLine(order_id=order.id, item_id=dosa.id, qty=1),
            OrderTransition(
                order_id=order.id,
                from_status=OrderStatus.PENDING_PAYMENT,
                to_status=OrderStatus.ACCEPTED,
                at=NOW - timedelta(hours=1),
            ),
        )
    proposal_id = _propose(
        engine,
        menu,
        ProposalType.PREP_PRIORITY,
        {"item_ids": [str(dosa.id), str(thali.id)]},
        slot=nxt,
    )

    assert _approve(api, proposal_id, admin).status_code == 200

    # Inside the first slot, so the proposal's slot is the next one.
    monkeypatch.setattr(clock, "now", lambda: WINDOW_START + timedelta(minutes=5))
    current_queue, next_queue = api.get("/api/v1/kitchen/queue", headers=_auth(admin)).json()[
        "slots"
    ]
    assert [line["name"] for line in next_queue["item_totals"]] == ["Dosa", "Thali"]
    assert next_queue["proposal_id"] == str(proposal_id)
    assert [line["name"] for line in current_queue["item_totals"]] == ["Thali", "Dosa"]


def test_prep_priority_for_an_item_with_no_pending_orders_is_invalidated(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _propose(
        engine,
        menu,
        ProposalType.PREP_PRIORITY,
        {"item_ids": [str(menu["dosa"].id)]},
        slot=menu["slots"][1],
    )

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 409
    assert response.json()["detail"]["proposal"]["status"] == "INVALIDATED"


def test_a_malformed_payload_is_invalidated(
    api: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    proposal_id = _propose(engine, menu, ProposalType.REPLENISH, {"lines": "forty Thali"})

    response = _approve(api, proposal_id, admin)

    assert response.status_code == 409
    assert response.json()["detail"]["proposal"]["status"] == "INVALIDATED"


def test_concurrent_decisions_exactly_one_succeeds(
    db_client: TestClient, engine: Engine, admin: User, menu: dict[str, Any]
) -> None:
    """UC-25 2c, through the service with one session per Administrator."""
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def decide(approve: bool) -> str:
        with factory() as session:
            service = ProposalService(session)
            try:
                if approve:
                    return service.approve(admin, proposal_id, NOW).status.value
                return service.reject(admin, proposal_id, "No", NOW).status.value
            except ProposalNotPendingError:
                return "409"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(decide, [True, False]))

    assert outcomes in (["409", "APPROVED"], ["409", "REJECTED"])
    assert _total(engine, menu["thali"]) == (140 if "APPROVED" in outcomes else 100)


def test_list_shows_pending_proposals_and_expires_stale_ones(
    api: TestClient,
    engine: Engine,
    admin: User,
    menu: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replenish = _replenish(engine, menu, (menu["thali"], 40))
    prep = _propose(
        engine,
        menu,
        ProposalType.PREP_PRIORITY,
        {"item_ids": [str(menu["thali"].id)]},
        slot=menu["slots"][1],
        created_at=NOW - timedelta(minutes=10),
    )

    listed = api.get(PROPOSALS, headers=_auth(admin))
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [str(prep), str(replenish)]
    assert listed.json()[0]["run_id"] == str(menu["run"].id)

    # Once the window opens, the replenishment's target has started; the 12:15 slot's has not.
    monkeypatch.setattr(clock, "now", lambda: WINDOW_START)
    assert [p["id"] for p in api.get(PROPOSALS, headers=_auth(admin)).json()] == [str(prep)]
    expired = api.get(PROPOSALS, params={"status": "EXPIRED"}, headers=_auth(admin)).json()
    assert [p["id"] for p in expired] == [str(replenish)]
    assert [row.action for row in _audit(engine, replenish)] == ["PROPOSAL_EXPIRED"]


def test_the_worker_expires_stale_proposals(
    configured_database: None,
    db_client: TestClient,
    engine: Engine,
    menu: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))
    assert "proposal-expiry" in {job.name for job in all_jobs()}
    assert PROPOSAL_JOBS[0].func is expire_proposals

    monkeypatch.setattr(clock, "now", lambda: NOW)
    expire_proposals()
    assert _proposal(engine, proposal_id).status is ProposalStatus.PENDING
    monkeypatch.setattr(clock, "now", lambda: WINDOW_START)
    expire_proposals()
    assert _proposal(engine, proposal_id).status is ProposalStatus.EXPIRED


def test_only_the_administrator_decides(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    proposal_id = _replenish(engine, menu, (menu["thali"], 40))
    kitchen = _auth(_user(engine, Role.KITCHEN))

    assert api.get(PROPOSALS, headers=kitchen).status_code == 403
    assert api.post(f"{PROPOSALS}/{proposal_id}/approve", headers=kitchen).status_code == 403
    assert (
        api.post(
            f"{PROPOSALS}/{uuid.uuid4()}/approve", headers=_auth(_user(engine, Role.ADMIN))
        ).status_code
        == 404
    )
    assert _proposal(engine, proposal_id).status is ProposalStatus.PENDING
