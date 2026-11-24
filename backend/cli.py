"""Local administration: python -m backend.cli create-user --username admin --role administrator

The password is read from SWARM_NEW_USER_PASSWORD or an interactive prompt, never argv.
"""

import argparse
import getpass
import os
import sys

from backend.core.config import load_settings
from backend.core.permissions import GlobalRole
from backend.database.session import Database, build_engine
from backend.services import audit
from backend.services.auth import AuthService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="create a user (first administrator, etc.)")
    create.add_argument("--username", required=True)
    create.add_argument("--role", choices=[r.value for r in GlobalRole], required=True)
    create.add_argument("--display-name")
    args = parser.parse_args(argv)

    settings = load_settings()
    db = Database(build_engine(settings))
    if db.migration_revision() is None:
        print("database is not migrated; run: python -m alembic upgrade head", file=sys.stderr)
        return 2
    password = os.environ.get("SWARM_NEW_USER_PASSWORD") or getpass.getpass("Password: ")
    service = AuthService(db, settings)
    with db.transaction() as session:
        user = service.create_user(
            session, args.username, password, GlobalRole(args.role), args.display_name
        )
        audit.record(
            session,
            None,
            "user.create",
            resource_type="user",
            resource_id=user.id,
            actor="local-cli",
            details={"username": user.username, "global_role": user.global_role},
        )
        print(f"created {user.global_role} {user.username} ({user.id})")
    db.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
