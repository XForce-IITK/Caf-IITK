"""Subsidy settings and Student eligibility (FR-23 / US-18).

The Administrator sets P-SUBSIDY_AMT and P-SUBSIDY_CAP_PCT and marks Students
eligible; the pricing engine applies them to the next quote (FR-24 step 4).
Orders already placed keep their price snapshots (FR-27). Every change is
audited (FR-47); a request that changes nothing writes nothing.
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import Role
from app.models.identity import User
from app.models.platform import Setting
from app.modules.audit.service import write_audit
from app.modules.pricing.repository import PricingRepository
from app.modules.pricing.schemas import StudentOut, SubsidySettings

# Field of SubsidySettings -> its row in `settings`.
_KEYS = {"amount_paise": "P-SUBSIDY_AMT_PAISE", "cap_pct": "P-SUBSIDY_CAP_PCT"}


class StudentNotFoundError(Exception):
    pass


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SubsidyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_settings(self) -> SubsidySettings:
        with self.session.begin():
            rows = PricingRepository(self.session).get_settings(*_KEYS.values())
            return SubsidySettings(**{field: int(rows[key]) for field, key in _KEYS.items()})

    def set_settings(self, admin: User, request: SubsidySettings) -> SubsidySettings:
        with self.session.begin():
            rows = {
                row.key: row
                for row in self.session.scalars(
                    select(Setting)
                    .where(Setting.key.in_(_KEYS.values()))
                    .order_by(Setting.key)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            }
            before = {field: int(rows[key].value) for field, key in _KEYS.items()}
            after = request.model_dump()
            changed = sorted(field for field in _KEYS if after[field] != before[field])
            if changed:
                for field in changed:
                    rows[_KEYS[field]].value = after[field]
                write_audit(
                    self.session,
                    action="SUBSIDY_SETTINGS_UPDATED",
                    entity_type="settings",
                    entity_id="subsidy",
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    before={field: before[field] for field in changed},
                    after={field: after[field] for field in changed},
                )
            return request

    def list_students(
        self, *, search: str | None, eligible: bool | None, limit: int
    ) -> list[StudentOut]:
        query = select(User).where(User.role == Role.STUDENT)
        if search:
            pattern = _like(search)
            query = query.where(
                or_(User.email.ilike(pattern, escape="\\"), User.name.ilike(pattern, escape="\\"))
            )
        if eligible is not None:
            query = query.where(User.subsidy_eligible.is_(eligible))
        with self.session.begin():
            rows = self.session.scalars(query.order_by(User.name, User.email).limit(limit))
            return [StudentOut.model_validate(row) for row in rows]

    def set_eligibility(self, admin: User, student_id: uuid.UUID, *, eligible: bool) -> StudentOut:
        """Only Students can be eligible. A deactivated Student can still be marked,
        so eligibility is in place if the account is reactivated."""
        with self.session.begin():
            student = self.session.scalars(
                select(User)
                .where(User.id == student_id, User.role == Role.STUDENT)
                # As placement locks it (OrderRepository.lock_student): waits for
                # an in-flight placement, so that order is priced with one value.
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            ).one_or_none()
            if student is None:
                raise StudentNotFoundError
            if student.subsidy_eligible != eligible:
                student.subsidy_eligible = eligible
                write_audit(
                    self.session,
                    action="SUBSIDY_ELIGIBILITY_UPDATED",
                    entity_type="user",
                    entity_id=str(student.id),
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    before={"subsidy_eligible": not eligible},
                    after={"subsidy_eligible": eligible},
                )
            return StudentOut.model_validate(student)
