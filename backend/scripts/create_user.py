"""Interactively create the first application user (an administrator).

Run from the backend directory:

    python scripts/create_user.py

The password is entered with getpass and is never echoed or passed on the
command line. No credentials are stored in this file.
"""

import getpass
import sys
from pathlib import Path

# Allow "python scripts/create_user.py" to import the app package.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from email_validator import EmailNotValidError, validate_email  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError, SQLAlchemyError  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024


def prompt_full_name() -> str:
    while True:
        full_name = input("Full name: ").strip()
        if full_name:
            if len(full_name) > 255:
                print("Name must be 255 characters or fewer.")
                continue
            return full_name
        print("Name is required.")


def prompt_email() -> str:
    while True:
        raw_email = input("Email: ").strip()
        try:
            # check_deliverability=False avoids a network lookup during setup.
            return validate_email(
                raw_email, check_deliverability=False
            ).normalized.lower()
        except EmailNotValidError as exc:
            print(f"Invalid email: {exc}")


def prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
            continue
        if len(password) > MAX_PASSWORD_LENGTH:
            print(
                f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
            )
            continue

        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match. Try again.")
            continue
        return password


def main() -> int:
    print("Create the first CLM administrator account")
    full_name = prompt_full_name()
    email = prompt_email()
    password = prompt_password()

    try:
        with SessionLocal() as db:
            existing = db.execute(
                select(User).where(User.email == email)
            ).scalar_one_or_none()
            if existing is not None:
                print("An account with that email already exists.")
                return 1

            user = User(
                full_name=full_name,
                email=email,
                password_hash=hash_password(password),
                # "admin" is one of the values allowed by ck_users_role.
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                # Covers a duplicate email created between the check and insert.
                db.rollback()
                print("An account with that email already exists.")
                return 1
    except SQLAlchemyError as exc:
        print("Could not create the user.")
        print(f"  {type(exc).__name__}: {exc}")
        return 1

    print(f"Created administrator account: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
