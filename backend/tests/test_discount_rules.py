"""US-17 (CAFIITK-142, FR-22) acceptance tests TC-US17-AC1..AC2, via /api/v1/admin/discount-rules.

The Administrator creates, edits and deactivates time-of-day discount rules; the
next quote prices with them (FR-24). A rule covers slots starting in
[start_time, end_time) (E28).
"""

import uuid
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import DiscountRule, MenuItem
from app.models.enums import ItemCategory, ItemStatus, Role
from app.models.identity import User
from app.models.platform import AuditLog

URL = "/api/v1/admin/discount-rules"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
EARLY_BIRD = {
    "name": "Early bird",
    "start_time": "12:00",
    "end_time": "12:30",
    "pct": 20,
    "scope": "CATEGORY",
    "category": "BEVERAGE",
}


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _headers(engine: Engine, role: Role) -> dict[str, str]:
    user = User(
        id=uuid.uuid4(),
        name="Asha",
        email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
    )
    _add(engine, user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture
def admin(engine: Engine) -> dict[str, str]:
    return _headers(engine, Role.ADMIN)


@pytest.fixture
def menu(engine: Engine) -> dict[str, Any]:
    """Thali (meal) Rs 80 and Tea (beverage) Rs 15; slots at 12:00, 12:15 and 12:30."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
    gone = MenuItem(
        id=uuid.uuid4(),
        name="Old Lassi",
        category=ItemCategory.BEVERAGE,
        price_paise=3000,
        status=ItemStatus.REMOVED,
    )
    day = ServiceDay(
        service_date=DAY,
        window_start=time(12, 0),
        window_end=time(14, 30),
        slot_len_min=15,
        default_capacity=30,
    )
    slots = {
        minute: Slot(
            id=uuid.uuid4(),
            service_date=DAY,
            starts_at=datetime(2026, 10, 6, 12, minute, tzinfo=IST),
            ends_at=datetime(2026, 10, 6, 12, minute + 15, tzinfo=IST),
            capacity=30,
        )
        for minute in (0, 15, 30)
    }
    _add(engine, thali, tea, gone, day)
    _add(
        engine,
        *slots.values(),
        DailyInventory(item_id=thali.id, service_date=DAY, total=50),
        DailyInventory(item_id=tea.id, service_date=DAY, total=50),
    )
    return {"thali": thali, "tea": tea, "gone": gone, "slots": slots}


def _discounts(
    client: TestClient, engine: Engine, menu: dict[str, Any], minute: int
) -> dict[str, int]:
    """The discount percentage of each line of a Thali-and-Tea quote for the 12:mm slot."""
    response = client.post(
        "/api/v1/quotes",
        json={
            "slot_id": str(menu["slots"][minute].id),
            "lines": [
                {"item_id": str(menu["thali"].id), "qty": 1},
                {"item_id": str(menu["tea"].id), "qty": 1},
            ],
        },
        headers=_headers(engine, Role.STUDENT),
    )
    assert response.status_code == 200, response.text
    return {line["name"]: line["discount_pct"] for line in response.json()["lines"]}


def _errors(response: Any) -> dict[str, str]:
    assert response.status_code == 422, response.text
    return {error["loc"][-1]: error["msg"] for error in response.json()["detail"]}


def _rule_count(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(DiscountRule)) or 0


def _audit(engine: Engine, rule_id: str) -> list[AuditLog]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog).where(AuditLog.entity_id == rule_id).order_by(AuditLog.id)
            )
        )


# --- Acceptance criteria ----------------------------------------------------------------


def test_tc_us17_ac1_early_bird_beverages_are_quoted_20_percent_off(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    response = db_client.post(URL, json=EARLY_BIRD, headers=admin)

    assert response.status_code == 201, response.text
    for minute in (0, 15):
        assert _discounts(db_client, engine, menu, minute) == {"Thali": 0, "Tea": 20}
    # E28: the range is half-open, so the slot starting at 12:30 is not discounted.
    assert _discounts(db_client, engine, menu, 30) == {"Thali": 0, "Tea": 0}


def test_tc_us17_ac2_a_60_percent_rule_is_422_and_nothing_is_created(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    response = db_client.post(URL, json={**EARLY_BIRD, "pct": 60}, headers=admin)

    assert "pct" in _errors(response)
    assert _rule_count(engine) == 0


# --- Creating ---------------------------------------------------------------------------


@pytest.mark.parametrize(("pct", "status"), [(0, 422), (1, 201), (50, 201), (51, 422)])
def test_percentage_bounds_are_1_to_50(
    db_client: TestClient, admin: dict[str, str], pct: int, status: int
) -> None:
    assert db_client.post(URL, json={**EARLY_BIRD, "pct": pct}, headers=admin).status_code == status


def test_a_created_rule_is_returned_active_and_audited(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    response = db_client.post(URL, json={**EARLY_BIRD, "name": "  Early bird  "}, headers=admin)

    rule = response.json()
    assert {k: v for k, v in rule.items() if k not in ("id", "created_at")} == {
        "name": "Early bird",
        "start_time": "12:00:00",
        "end_time": "12:30:00",
        "pct": 20,
        "scope": "CATEGORY",
        "category": "BEVERAGE",
        "item_ids": [],
        "active": True,
    }
    [entry] = _audit(engine, rule["id"])
    assert (entry.action, entry.entity_type, entry.actor_role) == (
        "DISCOUNT_RULE_CREATED",
        "discount_rule",
        "ADMIN",
    )
    assert entry.after == {
        "name": "Early bird",
        "start_time": "12:00:00",
        "end_time": "12:30:00",
        "pct": 20,
        "scope": "CATEGORY",
        "category": "BEVERAGE",
        "item_ids": [],
        "active": True,
    }


def test_an_items_rule_discounts_only_the_listed_items(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    body = {
        "name": "Thali hour",
        "start_time": "12:00",
        "end_time": "13:00",
        "pct": 15,
        "scope": "ITEMS",
        "item_ids": [str(menu["thali"].id)],
    }

    response = db_client.post(URL, json=body, headers=admin)

    assert response.status_code == 201, response.text
    assert response.json()["item_ids"] == [str(menu["thali"].id)]
    assert _discounts(db_client, engine, menu, 15) == {"Thali": 15, "Tea": 0}


def test_overlapping_rules_are_allowed_and_only_the_highest_applies(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    everything = {"name": "Lunch", "start_time": "11:30", "end_time": "13:00", "pct": 10}
    assert (
        db_client.post(URL, json={**everything, "scope": "ALL"}, headers=admin).status_code == 201
    )
    assert db_client.post(URL, json=EARLY_BIRD, headers=admin).status_code == 201

    assert _discounts(db_client, engine, menu, 15) == {"Thali": 10, "Tea": 20}


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"end_time": "12:00"}, "end_time"),  # empty range
        ({"end_time": "11:00"}, "end_time"),  # backwards
        ({"start_time": "12:00+05:30"}, "start_time"),  # times are IST wall-clock
        ({"category": None}, "category"),  # CATEGORY without a category
        ({"scope": "ALL"}, "category"),  # ALL with a category
        ({"name": "   "}, "name"),
        ({"name": "x" * 61}, "name"),
        ({"pct": "twenty"}, "pct"),
        ({"scope": "SOME"}, "scope"),
    ],
)
def test_an_invalid_rule_is_a_field_level_422(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    change: dict[str, Any],
    field: str,
) -> None:
    response = db_client.post(URL, json={**EARLY_BIRD, **change}, headers=admin)

    assert field in _errors(response)
    assert _rule_count(engine) == 0


def test_items_rules_need_known_active_distinct_items(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    body = {**EARLY_BIRD, "scope": "ITEMS", "category": None}
    tea = str(menu["tea"].id)

    assert "item_ids" in _errors(db_client.post(URL, json=body, headers=admin))  # none
    for item_ids in ([str(uuid.uuid4())], [str(menu["gone"].id)], [tea, tea]):
        response = db_client.post(URL, json={**body, "item_ids": item_ids}, headers=admin)
        assert "item_ids" in _errors(response), item_ids
    assert "item_ids" in _errors(
        db_client.post(URL, json={**EARLY_BIRD, "item_ids": [tea]}, headers=admin)
    )
    assert _rule_count(engine) == 0


def test_every_problem_is_reported_at_once(db_client: TestClient, admin: dict[str, str]) -> None:
    body = {**EARLY_BIRD, "end_time": "11:00", "scope": "ITEMS"}

    errors = _errors(db_client.post(URL, json=body, headers=admin))

    assert set(errors) == {"end_time", "category", "item_ids"}


# --- Listing, editing and deactivating ----------------------------------------------------


def _create(client: TestClient, admin: dict[str, str], **change: Any) -> dict[str, Any]:
    response = client.post(URL, json={**EARLY_BIRD, **change}, headers=admin)
    assert response.status_code == 201, response.text
    rule: dict[str, Any] = response.json()
    return rule


def test_listing_returns_every_rule_by_start_time_including_inactive_ones(
    db_client: TestClient, admin: dict[str, str]
) -> None:
    late = _create(db_client, admin, name="Late lunch", start_time="13:30", end_time="14:30")
    early = _create(db_client, admin)
    db_client.patch(f"{URL}/{late['id']}", json={"active": False}, headers=admin)

    response = db_client.get(URL, headers=admin)

    assert response.status_code == 200
    assert [(r["id"], r["active"]) for r in response.json()] == [
        (early["id"], True),
        (late["id"], False),
    ]


def test_an_edit_reaches_the_next_quote_and_is_audited_field_by_field(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    rule = _create(db_client, admin)

    response = db_client.patch(
        f"{URL}/{rule['id']}",
        json={"pct": 30, "end_time": "12:45", "name": "Early bird"},
        headers=admin,
    )

    assert response.status_code == 200, response.text
    assert (response.json()["pct"], response.json()["end_time"]) == (30, "12:45:00")
    assert _discounts(db_client, engine, menu, 30) == {"Thali": 0, "Tea": 30}
    _, entry = _audit(engine, rule["id"])
    assert entry.action == "DISCOUNT_RULE_UPDATED"
    # The unchanged name is not recorded.
    assert entry.before == {"end_time": "12:30:00", "pct": 20}
    assert entry.after == {"end_time": "12:45:00", "pct": 30}


def test_a_deactivated_rule_stops_applying_and_can_be_reactivated(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    rule = _create(db_client, admin)

    off = db_client.patch(f"{URL}/{rule['id']}", json={"active": False}, headers=admin)

    assert off.json()["active"] is False
    assert _discounts(db_client, engine, menu, 0) == {"Thali": 0, "Tea": 0}
    db_client.patch(f"{URL}/{rule['id']}", json={"active": True}, headers=admin)
    assert _discounts(db_client, engine, menu, 0) == {"Thali": 0, "Tea": 20}
    _, deactivated, _ = _audit(engine, rule["id"])
    assert (deactivated.before, deactivated.after) == ({"active": True}, {"active": False})


def test_changing_the_scope_drops_the_old_scopes_category_and_items(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    rule = _create(db_client, admin)
    url = f"{URL}/{rule['id']}"

    to_all = db_client.patch(url, json={"scope": "ALL"}, headers=admin).json()
    assert (to_all["scope"], to_all["category"]) == ("ALL", None)
    assert _discounts(db_client, engine, menu, 0) == {"Thali": 20, "Tea": 20}

    thali = str(menu["thali"].id)
    to_items = db_client.patch(url, json={"scope": "ITEMS", "item_ids": [thali]}, headers=admin)
    assert to_items.json()["item_ids"] == [thali]
    assert _discounts(db_client, engine, menu, 0) == {"Thali": 20, "Tea": 0}

    back = db_client.patch(url, json={"scope": "CATEGORY", "category": "BEVERAGE"}, headers=admin)
    assert (back.json()["category"], back.json()["item_ids"]) == ("BEVERAGE", [])
    assert _discounts(db_client, engine, menu, 0) == {"Thali": 0, "Tea": 20}


def test_an_item_removed_after_being_listed_does_not_block_other_edits(
    db_client: TestClient, engine: Engine, menu: dict[str, Any], admin: dict[str, str]
) -> None:
    rule = _create(db_client, admin, scope="ITEMS", category=None, item_ids=[str(menu["tea"].id)])
    with Session(engine) as session, session.begin():
        session.get_one(MenuItem, menu["tea"].id).status = ItemStatus.REMOVED

    response = db_client.patch(f"{URL}/{rule['id']}", json={"pct": 25}, headers=admin)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"category": "SNACK", "scope": "ALL"}, "category"),
        ({"item_ids": [str(uuid.uuid4())]}, "item_ids"),  # still a CATEGORY rule
        ({"start_time": "12:30"}, "end_time"),  # now empty
        ({"pct": None}, "body"),
        ({}, "body"),
        ({"pct": 51}, "pct"),
    ],
)
def test_an_invalid_edit_is_422_and_changes_nothing(
    db_client: TestClient,
    engine: Engine,
    admin: dict[str, str],
    body: dict[str, Any],
    field: str,
) -> None:
    rule = _create(db_client, admin)

    response = db_client.patch(f"{URL}/{rule['id']}", json=body, headers=admin)

    if field == "body":
        assert response.status_code == 422
    else:
        assert field in _errors(response)
    [listed] = db_client.get(URL, headers=admin).json()
    assert listed == rule
    assert len(_audit(engine, rule["id"])) == 1


def test_an_edit_that_changes_nothing_writes_no_audit_entry(
    db_client: TestClient, engine: Engine, admin: dict[str, str]
) -> None:
    rule = _create(db_client, admin)

    response = db_client.patch(f"{URL}/{rule['id']}", json={"pct": 20}, headers=admin)

    assert response.status_code == 200
    assert len(_audit(engine, rule["id"])) == 1


def test_editing_an_unknown_rule_is_404(db_client: TestClient, admin: dict[str, str]) -> None:
    response = db_client.patch(f"{URL}/{uuid.uuid4()}", json={"pct": 10}, headers=admin)

    assert response.status_code == 404


# --- Permissions (FR-6) -------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN])
def test_only_the_administrator_manages_discount_rules(
    db_client: TestClient, engine: Engine, admin: dict[str, str], role: Role
) -> None:
    rule = _create(db_client, admin)
    headers = _headers(engine, role)

    assert db_client.get(URL, headers=headers).status_code == 403
    assert db_client.post(URL, json=EARLY_BIRD, headers=headers).status_code == 403
    patch = db_client.patch(f"{URL}/{rule['id']}", json={"pct": 50}, headers=headers)
    assert patch.status_code == 403
    assert _rule_count(engine) == 1
