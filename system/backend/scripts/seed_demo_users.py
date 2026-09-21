"""Create preserved local demo users from environment-provided passwords."""
import json

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.models import User
from app.repositories.user_repository import UserRepository
from app.security.passwords import hash_password

DEMO_USERS = (
    ("admin_demo", "ADMIN", "demo_admin_password"),
    ("pm_demo", "PRODUCT_MANAGER", "demo_pm_password"),
    ("sales_demo", "SALES", "demo_sales_password"),
)


def seed() -> dict:
    settings = get_settings()
    missing = [field.upper() for _, _, field in DEMO_USERS if getattr(settings, field) is None]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    result = {"created": 0, "existing": 0, "usernames": []}
    with Session(get_engine()) as session:
        repository = UserRepository()
        for username, role, password_field in DEMO_USERS:
            result["usernames"].append(username)
            if repository.get_by_username(session, username) is not None:
                result["existing"] += 1
                continue
            password = getattr(settings, password_field)
            session.add(User(username=username, password_hash=hash_password(password.get_secret_value()), role=role, status="ACTIVE"))
            result["created"] += 1
        session.commit()
    return result


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False))
