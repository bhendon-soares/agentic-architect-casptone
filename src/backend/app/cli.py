"""Explicit, operator-controlled identity and legacy-data commands."""

import argparse
import getpass
import os

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.auth import hasher, normalized_email, validate_password
from app.persistence.models import LoginAttempt, User, utc_now

PURGE_ORDER = (
    "agent_events", "agent_run_attempts", "agent_run_telemetry",
    "agent_run_results_summary", "chat_messages", "tickets", "agent_runs",
    "chat_sessions",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create_admin = commands.add_parser("create-admin")
    create_admin.add_argument("--email", required=True)
    create_admin.add_argument("--name", required=True)
    unlock = commands.add_parser("unlock-login")
    unlock.add_argument("--email", required=True)
    unlock.add_argument("--ip")
    purge = commands.add_parser("purge-legacy")
    purge.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    if args.command == "purge-legacy":
        with engine.begin() as connection:
            for table in PURGE_ORDER:
                count = connection.scalar(text(f"SELECT count(*) FROM {table}"))
                print(f"{table}: {count}")
            if not args.confirm:
                print("No data deleted. Back up the database, then use --confirm.")
                return
            for table in PURGE_ORDER:
                connection.execute(text(f"DELETE FROM {table}"))
        return
    with Session(engine) as db:
        if args.command == "create-admin":
            email = normalized_email(args.email)
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                if existing.role != "admin":
                    raise RuntimeError("Seed email belongs to a non-admin user")
                print("Admin seed already exists; no changes made.")
                return
            password = getpass.getpass("New admin password (12+ characters): ")
            validate_password(password)
            db.add(User(email=email, display_name=args.name,
                        role="admin", password_hash=hasher.hash(password),
                        password_changed_at=utc_now(), must_change_password=False))
            db.commit()
            print("Admin created.")
        else:
            query = select(LoginAttempt).where(
                LoginAttempt.email_normalized == normalized_email(args.email),
                LoginAttempt.locked_at.is_not(None), LoginAttempt.unlocked_at.is_(None)
            )
            if args.ip:
                query = query.where(LoginAttempt.ip == args.ip)
            for attempt in db.scalars(query):
                attempt.unlocked_at = utc_now()
                attempt.failed_count = 0
            db.commit()
            print("Login locks cleared.")


if __name__ == "__main__":
    main()