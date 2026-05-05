"""Endpointy REST API do testowania notyfikacji email."""

from fastapi import APIRouter, Depends

from src.api.auth import require_role
from src.db.models import User, UserRole
from src.notifications.email_sender import EmailSender

router = APIRouter()


@router.post("/test")
async def send_test_email(
    _user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Wysyla testowy email alertowy — wymaga roli ADMIN."""
    sender = EmailSender()

    test_alert = {
        "id": "test-00000000",
        "alert_type": "theft_spike",
        "severity": "high",
        "title": "Test Alert — Transport Intelligence",
        "description": (
            "This is a test notification to verify that the email delivery "
            "system is working correctly. No action required."
        ),
        "country_codes": ["PL", "DE"],
        "region": "Test Region",
        "triggered_at": "2026-01-01 12:00 UTC",
        "related_events": [
            "Cargo theft reported near Warsaw (PL)",
            "Fuel theft in Brandenburg (DE)",
            "Vehicle damage on A2 motorway (PL)",
        ],
    }

    ok = await sender.send_alert_email(test_alert, [_user.email])

    return {
        "status": "sent" if ok else "failed",
        "recipient": _user.email,
        "smtp_enabled": sender.enabled,
        "message": (
            "Test email sent successfully"
            if ok
            else "Failed to send test email — check SMTP configuration"
        ),
    }
