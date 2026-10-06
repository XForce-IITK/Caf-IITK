"""Deployment-time seed of the first Administrator and a Kitchen Staff account (FR-2).

Run after migrations: `python -m app.seed`. Reads CAF_SEED_ADMIN_EMAIL /
CAF_SEED_ADMIN_PASSWORD and CAF_SEED_KITCHEN_EMAIL / CAF_SEED_KITCHEN_PASSWORD.
An account whose variables are unset is skipped; an existing email is left
unchanged, so the command is safe to run on every deployment.
"""

from app.core.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.models.enums import Role
from app.modules.identity.service import IdentityService

MIN_PASSWORD_LENGTH = 8


def seed(settings: Settings) -> list[str]:
    accounts = [
        ("Administrator", settings.seed_admin_email, settings.seed_admin_password, Role.ADMIN),
        (
            "Kitchen Staff",
            settings.seed_kitchen_email,
            settings.seed_kitchen_password,
            Role.KITCHEN,
        ),
    ]
    report = []
    for name, email, password, role in accounts:
        if not email or not password:
            report.append(f"{role.value}: skipped (not configured)")
            continue
        if len(password) < MIN_PASSWORD_LENGTH:
            raise SystemExit(f"{role.value} seed password must be at least 8 characters")
        with get_sessionmaker()() as session:
            created = IdentityService(session).ensure_account(
                name=name, email=email, password=password, role=role
            )
        report.append(f"{role.value}: {'created' if created else 'already exists'}")
    return report


def main() -> None:
    for line in seed(get_settings()):
        print(line)


if __name__ == "__main__":
    main()
