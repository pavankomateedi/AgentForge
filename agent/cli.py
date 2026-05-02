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

import asyncio

from agent import audit, auth, email as email_module, rbac
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


def cmd_send_test_email(args: argparse.Namespace) -> None:
    config = get_config()
    if not config.resend_api_key or not config.resend_from:
        print(
            "ERROR: RESEND_API_KEY and RESEND_FROM must both be set in .env "
            "(or in the Railway Variables tab) before sending a test email.",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        asyncio.run(
            email_module.send_test_email(
                api_key=config.resend_api_key,
                from_addr=config.resend_from,
                to_addr=args.email,
            )
        )
    except email_module.EmailSendError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Test email sent to {args.email}.")


def cmd_reset_mfa(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    user = auth.get_user_by_username(config.database_url, args.username)
    if user is None:
        print(f"No user named {args.username!r}", file=sys.stderr)
        sys.exit(1)
    auth.reset_mfa(config.database_url, user.id)
    print(f"MFA reset for {args.username}; they will re-enroll on next login.")


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


def cmd_assign_patient(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    user = auth.get_user_by_username(config.database_url, args.username)
    if user is None:
        print(f"No user named {args.username!r}", file=sys.stderr)
        sys.exit(1)
    rbac.assign_patient(
        config.database_url,
        user_id=user.id,
        patient_id=args.patient_id,
    )
    audit.record(
        config.database_url,
        audit.AuditEvent.PATIENT_ASSIGNED,
        user_id=user.id,
        details={"patient_id": args.patient_id, "by": "cli"},
    )
    print(f"Assigned {args.username} -> {args.patient_id}.")


def cmd_revoke_patient(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    user = auth.get_user_by_username(config.database_url, args.username)
    if user is None:
        print(f"No user named {args.username!r}", file=sys.stderr)
        sys.exit(1)
    rbac.revoke_assignment(
        config.database_url,
        user_id=user.id,
        patient_id=args.patient_id,
    )
    audit.record(
        config.database_url,
        audit.AuditEvent.PATIENT_UNASSIGNED,
        user_id=user.id,
        details={"patient_id": args.patient_id, "by": "cli"},
    )
    print(f"Revoked {args.username} -> {args.patient_id}.")


def cmd_list_assignments(args: argparse.Namespace) -> None:
    config = get_config()
    init_db(config.database_url)
    user = auth.get_user_by_username(config.database_url, args.username)
    if user is None:
        print(f"No user named {args.username!r}", file=sys.stderr)
        sys.exit(1)
    patients = rbac.list_assigned_patients(
        config.database_url, user_id=user.id
    )
    if not patients:
        print(f"{args.username} has no patient assignments.")
        return
    print(f"{args.username} ({user.role}) is assigned to:")
    for p in patients:
        print(f"  - {p}")


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

    p_resetmfa = sub.add_parser(
        "reset-mfa", help="Clear a user's MFA enrollment so they re-enroll on next login."
    )
    p_resetmfa.add_argument("username")
    p_resetmfa.set_defaults(func=cmd_reset_mfa)

    p_test_email = sub.add_parser(
        "send-test-email",
        help="Send a test email via Resend to verify your setup. Requires RESEND_API_KEY + RESEND_FROM.",
    )
    p_test_email.add_argument("email", help="Recipient email address")
    p_test_email.set_defaults(func=cmd_send_test_email)

    p_assign = sub.add_parser(
        "assign-patient",
        help="Grant a user access to a patient. Required for /chat to succeed.",
    )
    p_assign.add_argument("username")
    p_assign.add_argument("patient_id")
    p_assign.set_defaults(func=cmd_assign_patient)

    p_revoke = sub.add_parser(
        "revoke-patient",
        help="Remove a user's access to a patient.",
    )
    p_revoke.add_argument("username")
    p_revoke.add_argument("patient_id")
    p_revoke.set_defaults(func=cmd_revoke_patient)

    p_list_a = sub.add_parser(
        "list-assignments",
        help="Show which patients a user is assigned to.",
    )
    p_list_a.add_argument("username")
    p_list_a.set_defaults(func=cmd_list_assignments)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
