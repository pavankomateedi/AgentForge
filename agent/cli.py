"""Admin CLI: provision and manage users.

Usage:
    python -m agent.cli create-user dr.chen drchen@example.com
    python -m agent.cli list-users
    python -m agent.cli unlock dr.chen
    python -m agent.cli reset-password dr.chen
    python -m agent.cli deactivate dr.chen
"""

from __future__ import annotations

import argparse
import getpass
import sys

from agent import auth
from agent.config import get_config
from agent.db import connect, init_db


def _password_prompt(confirm: bool = True) -> str:
    pw = getpass.getpass("Password: ")
    if confirm:
        again = getpass.getpass("Confirm password: ")
        if pw != again:
            print("Passwords do not match.", file=sys.stderr)
            sys.exit(2)
    if len(pw) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(2)
    return pw


def cmd_create_user(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    pw = _password_prompt(confirm=True)
    user = auth.create_user(
        config.database_url,
        username=args.username,
        email=args.email,
        password=pw,
        role=args.role,
    )
    print(f"User created: id={user.id} username={user.username} role={user.role}")


def cmd_list_users(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    with connect(config.database_url) as conn:
        rows = conn.execute(
            """SELECT id, username, email, role, is_active, totp_enrolled,
                      failed_login_attempts, locked_until, created_at
               FROM users ORDER BY id"""
        ).fetchall()
    if not rows:
        print("(no users)")
        return
    print(f"{'id':<4} {'username':<20} {'email':<30} {'role':<12} active mfa locked")
    print("-" * 96)
    for r in rows:
        active = "yes" if r["is_active"] else "no"
        mfa = "yes" if r["totp_enrolled"] else "no"
        locked = r["locked_until"] or "-"
        print(
            f"{r['id']:<4} {r['username']:<20} {r['email']:<30} "
            f"{r['role']:<12} {active:<6} {mfa:<3} {locked}"
        )


def cmd_unlock(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    with connect(config.database_url) as conn:
        cur = conn.execute(
            """UPDATE users
               SET failed_login_attempts = 0,
                   locked_until = NULL,
                   updated_at = datetime('now')
               WHERE username = ?""",
            (args.username,),
        )
        conn.commit()
        if cur.rowcount == 0:
            print(f"No user named {args.username!r}", file=sys.stderr)
            sys.exit(1)
    print(f"Unlocked {args.username}.")


def cmd_reset_password(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    user = auth.get_user_by_username(config.database_url, args.username)
    if user is None:
        print(f"No user named {args.username!r}", file=sys.stderr)
        sys.exit(1)
    pw = _password_prompt(confirm=True)
    pwd_hash = auth.hash_password(pw)
    with connect(config.database_url) as conn:
        conn.execute(
            """UPDATE users
               SET password_hash = ?,
                   failed_login_attempts = 0,
                   locked_until = NULL,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (pwd_hash, user.id),
        )
        conn.commit()
    print(f"Password reset for {args.username}.")


def cmd_deactivate(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    with connect(config.database_url) as conn:
        cur = conn.execute(
            """UPDATE users
               SET is_active = 0, updated_at = datetime('now')
               WHERE username = ?""",
            (args.username,),
        )
        conn.commit()
        if cur.rowcount == 0:
            print(f"No user named {args.username!r}", file=sys.stderr)
            sys.exit(1)
    print(f"Deactivated {args.username}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent.cli", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-user", help="Create a new user.")
    p_create.add_argument("username")
    p_create.add_argument("email")
    p_create.add_argument("--role", default="physician")
    p_create.set_defaults(func=cmd_create_user)

    p_list = sub.add_parser("list-users", help="List all users.")
    p_list.set_defaults(func=cmd_list_users)

    p_unlock = sub.add_parser("unlock", help="Clear failed-attempt lockout.")
    p_unlock.add_argument("username")
    p_unlock.set_defaults(func=cmd_unlock)

    p_reset = sub.add_parser("reset-password", help="Reset a user's password.")
    p_reset.add_argument("username")
    p_reset.set_defaults(func=cmd_reset_password)

    p_deact = sub.add_parser("deactivate", help="Mark a user inactive.")
    p_deact.add_argument("username")
    p_deact.set_defaults(func=cmd_deactivate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
