"""US-18 (CAFIITK-143, FR-23) acceptance test TC-US18-AC1, via /api/v1/admin/subsidy,
/api/v1/admin/students and /api/v1/admin/users/{id}/eligibility.

The Administrator sets P-SUBSIDY_AMT and P-SUBSIDY_CAP_PCT and marks Students
subsidy-eligible; the Student's next quote includes the subsidy (FR-24 step 4).
"""

import uuid
from collections.abc import Iterator
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, Role
from app.models.identity import User
from app.models.platform import AuditLog, Setting

SUBSIDY = "/api/v1/admin/subsidy"
STUDENTS = "/api/v1/admin/students"
IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
KEYS = ("P-SUBSIDY_AMT_PAISE", "P-SUBSIDY_CAP_PCT")


def _eligibility(user_id: uuid.UUID | str) -> str:
    return f"/api/v1/admin/users/{user_id}/eligibility"


def _add(engine: Engine, *rows: Any) -> None:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.add_all(rows)


def _user(
    engine: Engine, role: Role, *, name: str = "Asha", email: str | None = None, **fields: Any
) -> User:
    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email or f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
        password_hash="unused",
        role=role,
        **fields,
    )
    _add(engine, user)
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


@pytest.fixture(autouse=True)
def _restore_subsidy_settings(engine: Engine) -> Iterator[None]:
    """Settings survive the per-test truncation, so put the seeded values back."""
    with Session(engine) as session:
        rows = session.scalars(select(Setting).where(Setting.key.in_(KEYS)))
        seeded = {row.key: row.value for row in rows}
    yield
    with Session(engine) as session, session.begin():
        for key, value in seeded.items():
            session.get_one(Setting, key).value = value


@pytest.fixture
def admin(engine: Engine) -> User:
    return _user(engine, Role.ADMIN)


@pytest.fixture
def student(engine: Engine) -> User:
    return _user(engine, Role.STUDENT, name="Sita")


@pytest.fixture
def slot(engine: Engine) -> dict[str, Any]:
    """Thali Rs 80 and Tea Rs 15, and the 12:15 slot; no discount rules."""
    thali = MenuItem(id=uuid.uuid4(), name="Thali", category=ItemCategory.MEAL, price_paise=8000)
    tea = MenuItem(id=uuid.uuid4(), name="Tea", category=ItemCategory.BEVERAGE, price_paise=1500)
    day = ServiceDay(
        service_date=DAY,
        window_start=time(12, 0),
        window_end=time(14, 30),
        slot_len_min=15,
        default_capacity=30,
    )
    slot = Slot(
        id=uuid.uuid4(),
        service_date=DAY,
        starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST),
        ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST),
        capacity=30,
    )
    _add(engine, thali, tea, day)
    _add(
        engine,
        slot,
        DailyInventory(item_id=thali.id, service_date=DAY, total=50),
        DailyInventory(item_id=tea.id, service_date=DAY, total=50),
    )
    return {"slot": slot, "thali": thali, "tea": tea}


def _quote(client: TestClient, student: User, slot: dict[str, Any], *, tea: int = 0) -> Any:
    """A quote for one Thali (Rs 80) and `tea` Teas (Rs 15 each) at 12:15."""
    lines = [{"item_id": str(slot["thali"].id), "qty": 1}]
    if tea:
        lines.append({"item_id": str(slot["tea"].id), "qty": tea})
    response = client.post(
        "/api/v1/quotes",
        json={"slot_id": str(slot["slot"].id), "lines": lines},
        headers=_auth(student),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _audit(engine: Engine, action: str, actor: User) -> list[AuditLog]:
    """By actor: audit_log keeps earlier tests' entries."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == action, AuditLog.actor_id == str(actor.id))
                .order_by(AuditLog.id)
            )
        )


def _errors(response: Any) -> dict[str, str]:
    assert response.status_code == 422, response.text
    return {str(error["loc"][-1]): error["msg"] for error in response.json()["detail"]}


# --- TC-US18-AC1 ----------------------------------------------------------------------


def test_tc_us18_ac1_marking_a_student_eligible_adds_a_subsidy_line_to_their_quote(
    db_client: TestClient, engine: Engine, admin: User, student: User, slot: dict[str, Any]
) -> None:
    # Given S is not eligible
    assert _quote(db_client, student, slot, tea=1)["subsidy_paise"] == 0

    # When I mark S eligible
    response = db_client.put(
        _eligibility(student.id), json={"eligible": True}, headers=_auth(admin)
    )
    assert response.status_code == 200, response.text
    assert response.json()["subsidy_eligible"] is True

    # And S requests a quote: Rs 95 less the Rs 20 subsidy (P-SUBSIDY_AMT, under the 50 % cap)
    quote = _quote(db_client, student, slot, tea=1)
    assert quote["discounted_subtotal_paise"] == 9500
    assert quote["subsidy_paise"] == 2000
    assert quote["payable_paise"] == 7500


def test_tc_us18_marking_a_student_not_eligible_removes_the_subsidy(
    db_client: TestClient, admin: User, engine: Engine, slot: dict[str, Any]
) -> None:
    student = _user(engine, Role.STUDENT, subsidy_eligible=True)
    assert _quote(db_client, student, slot)["subsidy_paise"] == 2000

    response = db_client.put(
        _eligibility(student.id), json={"eligible": False}, headers=_auth(admin)
    )

    assert response.json()["subsidy_eligible"] is False
    assert _quote(db_client, student, slot)["subsidy_paise"] == 0


def test_tc_us18_other_students_are_unaffected(
    db_client: TestClient, admin: User, student: User, engine: Engine, slot: dict[str, Any]
) -> None:
    other = _user(engine, Role.STUDENT)

    db_client.put(_eligibility(student.id), json={"eligible": True}, headers=_auth(admin))

    assert _quote(db_client, other, slot)["subsidy_paise"] == 0


# --- Subsidy settings -----------------------------------------------------------------


def test_tc_us18_the_settings_read_back_as_seeded(db_client: TestClient, admin: User) -> None:
    response = db_client.get(SUBSIDY, headers=_auth(admin))

    assert response.status_code == 200, response.text
    assert response.json() == {"amount_paise": 2000, "cap_pct": 50}


def test_tc_us18_a_new_amount_applies_to_the_next_quote(
    db_client: TestClient, admin: User, engine: Engine, slot: dict[str, Any]
) -> None:
    student = _user(engine, Role.STUDENT, subsidy_eligible=True)

    response = db_client.put(
        SUBSIDY, json={"amount_paise": 3000, "cap_pct": 50}, headers=_auth(admin)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"amount_paise": 3000, "cap_pct": 50}
    assert db_client.get(SUBSIDY, headers=_auth(admin)).json() == response.json()
    assert _quote(db_client, student, slot)["subsidy_paise"] == 3000


def test_tc_us18_a_new_cap_limits_the_subsidy_to_that_share_of_the_subtotal(
    db_client: TestClient, admin: User, engine: Engine, slot: dict[str, Any]
) -> None:
    student = _user(engine, Role.STUDENT, subsidy_eligible=True)

    db_client.put(SUBSIDY, json={"amount_paise": 3000, "cap_pct": 10}, headers=_auth(admin))

    quote = _quote(db_client, student, slot, tea=1)
    assert quote["subsidy_paise"] == 950  # 10 % of Rs 95, below the Rs 30 amount
    assert quote["payable_paise"] == 8600  # Rs 85.50 rounds half-up to Rs 86


def test_tc_us18_an_amount_of_zero_turns_the_subsidy_off(
    db_client: TestClient, admin: User, engine: Engine, slot: dict[str, Any]
) -> None:
    student = _user(engine, Role.STUDENT, subsidy_eligible=True)

    db_client.put(SUBSIDY, json={"amount_paise": 0, "cap_pct": 50}, headers=_auth(admin))

    assert _quote(db_client, student, slot)["subsidy_paise"] == 0


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"amount_paise": -1, "cap_pct": 50}, "amount_paise"),
        ({"amount_paise": 50_001, "cap_pct": 50}, "amount_paise"),
        ({"amount_paise": 20.5, "cap_pct": 50}, "amount_paise"),
        ({"amount_paise": 2000, "cap_pct": -1}, "cap_pct"),
        ({"amount_paise": 2000, "cap_pct": 101}, "cap_pct"),
        ({"amount_paise": 2000}, "cap_pct"),
        ({"amount_paise": 2000, "cap_pct": 50, "per_day": 2}, "per_day"),
    ],
    ids=["negative", "above-max", "fraction", "negative-cap", "cap-over-100", "missing", "unknown"],
)
def test_tc_us18_invalid_settings_are_a_field_level_422_and_change_nothing(
    db_client: TestClient, admin: User, body: dict[str, Any], field: str
) -> None:
    response = db_client.put(SUBSIDY, json=body, headers=_auth(admin))

    assert field in _errors(response)
    assert db_client.get(SUBSIDY, headers=_auth(admin)).json() == {
        "amount_paise": 2000,
        "cap_pct": 50,
    }


def test_tc_us18_the_bounds_themselves_are_accepted(db_client: TestClient, admin: User) -> None:
    for body in ({"amount_paise": 0, "cap_pct": 0}, {"amount_paise": 50_000, "cap_pct": 100}):
        assert db_client.put(SUBSIDY, json=body, headers=_auth(admin)).json() == body


def test_tc_us18_a_settings_change_audits_only_the_changed_fields(
    db_client: TestClient, admin: User, engine: Engine
) -> None:
    db_client.put(SUBSIDY, json={"amount_paise": 2500, "cap_pct": 50}, headers=_auth(admin))
    db_client.put(SUBSIDY, json={"amount_paise": 2500, "cap_pct": 50}, headers=_auth(admin))

    [entry] = _audit(engine, "SUBSIDY_SETTINGS_UPDATED", admin)
    assert (entry.entity_type, entry.entity_id) == ("settings", "subsidy")
    assert (entry.actor_id, entry.actor_role) == (str(admin.id), "ADMIN")
    assert (entry.before, entry.after) == ({"amount_paise": 2000}, {"amount_paise": 2500})


# --- Eligibility ----------------------------------------------------------------------


def test_tc_us18_an_eligibility_change_is_audited_once(
    db_client: TestClient, admin: User, student: User, engine: Engine
) -> None:
    for _ in range(2):  # the second request changes nothing
        db_client.put(_eligibility(student.id), json={"eligible": True}, headers=_auth(admin))

    [entry] = _audit(engine, "SUBSIDY_ELIGIBILITY_UPDATED", admin)
    assert (entry.entity_type, entry.entity_id) == ("user", str(student.id))
    assert (entry.actor_id, entry.actor_role) == (str(admin.id), "ADMIN")
    assert (entry.before, entry.after) == ({"subsidy_eligible": False}, {"subsidy_eligible": True})


def test_tc_us18_the_eligibility_response_describes_the_student(
    db_client: TestClient, admin: User, student: User
) -> None:
    response = db_client.put(
        _eligibility(student.id), json={"eligible": True}, headers=_auth(admin)
    )

    assert response.json() == {
        "id": str(student.id),
        "name": "Sita",
        "email": student.email,
        "is_active": True,
        "subsidy_eligible": True,
    }


def test_tc_us18_a_deactivated_student_can_still_be_marked(
    db_client: TestClient, admin: User, engine: Engine
) -> None:
    student = _user(engine, Role.STUDENT, is_active=False)

    response = db_client.put(
        _eligibility(student.id), json={"eligible": True}, headers=_auth(admin)
    )

    assert response.status_code == 200, response.text
    assert response.json()["subsidy_eligible"] is True


@pytest.mark.parametrize("role", [Role.KITCHEN, Role.ADMIN])
def test_tc_us18_staff_accounts_cannot_be_marked_eligible(
    db_client: TestClient, admin: User, engine: Engine, role: Role
) -> None:
    staff = _user(engine, role)

    response = db_client.put(_eligibility(staff.id), json={"eligible": True}, headers=_auth(admin))

    assert response.status_code == 404
    assert response.json() == {"detail": "Student not found"}
    assert _audit(engine, "SUBSIDY_ELIGIBILITY_UPDATED", admin) == []


def test_tc_us18_an_unknown_user_is_404(db_client: TestClient, admin: User) -> None:
    response = db_client.put(
        _eligibility(uuid.uuid4()), json={"eligible": True}, headers=_auth(admin)
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("body", "field"),
    [({}, "eligible"), ({"eligible": None}, "eligible"), ({"eligible": True, "x": 1}, "x")],
    ids=["missing", "null", "unknown"],
)
def test_tc_us18_an_invalid_eligibility_body_is_a_field_level_422(
    db_client: TestClient, admin: User, student: User, body: dict[str, Any], field: str
) -> None:
    response = db_client.put(_eligibility(student.id), json=body, headers=_auth(admin))

    assert field in _errors(response)


# --- Finding Students -----------------------------------------------------------------


@pytest.fixture
def students(engine: Engine) -> dict[str, User]:
    _user(engine, Role.KITCHEN, name="Anil Cook", email="anil@iitk.ac.in")
    return {
        "ravi": _user(engine, Role.STUDENT, name="Ravi Kumar", email="ravik@iitk.ac.in"),
        "meera": _user(
            engine, Role.STUDENT, name="Meera", email="meera_k@iitk.ac.in", subsidy_eligible=True
        ),
        "anu": _user(engine, Role.STUDENT, name="Anu", email="anu100%@iitk.ac.in"),
    }


def _names(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [student["name"] for student in response.json()]


def test_tc_us18_the_student_list_has_only_students_by_name(
    db_client: TestClient, admin: User, students: dict[str, User]
) -> None:
    assert _names(db_client.get(STUDENTS, headers=_auth(admin))) == ["Anu", "Meera", "Ravi Kumar"]


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("KUMAR", ["Ravi Kumar"]),  # name, any case
        ("ravik@", ["Ravi Kumar"]),  # email
        ("  meera ", ["Meera"]),  # surrounding spaces ignored
        ("_", ["Meera"]),  # a literal underscore, not "any character"
        ("%", ["Anu"]),  # a literal percent sign
        ("nobody", []),
    ],
)
def test_tc_us18_the_student_search_matches_part_of_the_name_or_email(
    db_client: TestClient,
    admin: User,
    students: dict[str, User],
    search: str,
    expected: list[str],
) -> None:
    response = db_client.get(STUDENTS, params={"search": search}, headers=_auth(admin))

    assert _names(response) == expected


def test_tc_us18_the_student_list_filters_by_eligibility(
    db_client: TestClient, admin: User, students: dict[str, User]
) -> None:
    def names(eligible: str) -> list[str]:
        return _names(db_client.get(STUDENTS, params={"eligible": eligible}, headers=_auth(admin)))

    assert names("true") == ["Meera"]
    assert names("false") == ["Anu", "Ravi Kumar"]


def test_tc_us18_the_student_list_is_limited(
    db_client: TestClient, admin: User, students: dict[str, User]
) -> None:
    assert _names(db_client.get(STUDENTS, params={"limit": 2}, headers=_auth(admin))) == [
        "Anu",
        "Meera",
    ]
    for limit in (0, 201):
        response = db_client.get(STUDENTS, params={"limit": limit}, headers=_auth(admin))
        assert "limit" in _errors(response)


# --- Authorisation --------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.STUDENT, Role.KITCHEN])
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", SUBSIDY, None),
        ("PUT", SUBSIDY, {"amount_paise": 1000, "cap_pct": 100}),
        ("GET", STUDENTS, None),
        ("PUT", "eligibility", {"eligible": True}),
    ],
    ids=["get-settings", "set-settings", "list-students", "set-eligibility"],
)
def test_tc_us18_only_the_administrator_manages_the_subsidy(
    db_client: TestClient,
    engine: Engine,
    student: User,
    role: Role,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    caller = student if role is Role.STUDENT else _user(engine, role)
    url = _eligibility(caller.id) if path == "eligibility" else path

    response = db_client.request(method, url, json=body, headers=_auth(caller))

    assert response.status_code == 403
    assert _audit(engine, "SUBSIDY_ELIGIBILITY_UPDATED", caller) == []
    assert _audit(engine, "SUBSIDY_SETTINGS_UPDATED", caller) == []


def test_tc_us18_an_anonymous_caller_is_401(db_client: TestClient) -> None:
    assert db_client.get(SUBSIDY).status_code == 401
