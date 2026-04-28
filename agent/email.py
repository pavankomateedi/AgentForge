"""Email sending via Resend.

Dev fallback: if RESEND_API_KEY (or RESEND_FROM) is unset, log the email body
to stdout instead of attempting delivery. Production deploys must set both.
"""

from __future__ import annotations

import logging

import httpx


log = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class EmailSendError(Exception):
    pass


async def _post_to_resend(
    api_key: str,
    payload: dict,
    *,
    timeout: float = 10.0,
) -> None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if res.status_code >= 400:
            raise EmailSendError(f"Resend API {res.status_code}: {res.text}")
    except httpx.HTTPError as exc:
        raise EmailSendError(f"Resend transport error: {exc}") from exc


async def send_test_email(
    *,
    api_key: str | None,
    from_addr: str | None,
    to_addr: str,
) -> None:
    """Tiny health-check email. Used by `python -m agent.cli send-test-email`."""
    if not api_key or not from_addr:
        raise EmailSendError(
            "RESEND_API_KEY and RESEND_FROM must both be set "
            "to send a test email."
        )
    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": "Clinical Co-Pilot — Resend test",
        "html": (
            "<p style='font-family:-apple-system,sans-serif;'>"
            "Resend is configured correctly. You can ignore this message."
            "</p>"
        ),
        "text": "Resend is configured correctly. You can ignore this message.",
    }
    await _post_to_resend(api_key, payload)
    log.info("test email sent to %s", to_addr)


def _password_reset_html(reset_url: str) -> str:
    return f"""<!doctype html>
<html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color:#0f172a; max-width:560px; margin:0 auto; padding:24px;">
  <h2 style="margin-top:0;">Reset your Clinical Co-Pilot password</h2>
  <p>You (or someone using your email address) requested a password reset for your Clinical Co-Pilot account.</p>
  <p>Click the link below to choose a new password. The link expires in <strong>1 hour</strong>.</p>
  <p style="margin: 28px 0;"><a href="{reset_url}" style="background:#2563eb; color:#ffffff; padding:10px 18px; border-radius:8px; text-decoration:none; font-weight:600;">Reset password</a></p>
  <p style="color:#64748b; font-size:13px;">If the button doesn't work, paste this URL into your browser:</p>
  <p style="color:#64748b; font-size:13px; word-break: break-all;">{reset_url}</p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 28px 0;">
  <p style="color:#94a3b8; font-size:12px;">If you didn't request this, you can safely ignore this email.</p>
</body></html>"""


def _password_reset_text(reset_url: str) -> str:
    return (
        "Reset your Clinical Co-Pilot password\n\n"
        "You requested a password reset. The link below expires in 1 hour.\n\n"
        f"{reset_url}\n\n"
        "If you didn't request this, ignore this email."
    )


async def send_password_reset_email(
    *,
    api_key: str | None,
    from_addr: str | None,
    to_addr: str,
    reset_url: str,
) -> None:
    subject = "Reset your Clinical Co-Pilot password"

    if not api_key or not from_addr:
        # Dev fallback — surface the link in the server logs so the operator
        # can copy/paste it. Useful when running locally without Resend set up.
        log.warning(
            "Resend not configured; password-reset email NOT sent. "
            "Reset link for %s: %s",
            to_addr,
            reset_url,
        )
        return

    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "html": _password_reset_html(reset_url),
        "text": _password_reset_text(reset_url),
    }
    await _post_to_resend(api_key, payload)
    log.info("password-reset email sent to %s", to_addr)
