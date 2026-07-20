import json
from typing import Any

from app.integrations.supabase_client import get_supabase_admin
from app.services.email_notifier import send_email


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def create_notification(business_id: str, channel: str, payload: dict[str, Any]) -> str | None:
    db = get_supabase_admin()
    resp = (
        db.table("notifications")
        .insert({"business_id": business_id, "channel": channel, "status": "queued", "payload": payload})
        .execute()
    )
    if getattr(resp, "data", None) and len(resp.data) > 0:
        return resp.data[0].get("id")
    return None


def mark_notification_status(notification_id: str, status: str, payload_update: dict[str, Any] | None = None) -> None:
    db = get_supabase_admin()
    updates: dict[str, Any] = {"status": status}
    if payload_update:
        updates["payload"] = payload_update
    db.table("notifications").update(updates).eq("id", notification_id).execute()


def notify_owner_lead_created(business_id: str, lead: dict[str, Any]) -> None:
    payload = {"type": "lead_created", "lead": lead}
    notification_id = create_notification(business_id, "email", payload)

    subject = "New lead captured (AI Receptionist)"
    body = "\n".join(
        [
            "A new lead was captured by the AI receptionist.",
            "",
            f"Name: {lead.get('full_name') or lead.get('fullName') or ''}",
            f"Phone: {lead.get('phone') or ''}",
            f"Intent: {lead.get('intent') or ''}",
            f"Location: {lead.get('location_interest') or lead.get('locationInterest') or ''}",
            f"Budget: {lead.get('budget_text') or lead.get('budget') or ''}",
            "",
            f"Raw: {_json_dump(lead)}",
        ]
    )

    try:
        send_email(subject, body)
        if notification_id:
            mark_notification_status(notification_id, "sent")
    except Exception as e:
        if notification_id:
            mark_notification_status(notification_id, "failed", {"type": "lead_created", "error": str(e), "lead": lead})


def notify_owner_appointment_booked(business_id: str, appointment: dict[str, Any]) -> None:
    payload = {"type": "appointment_booked", "appointment": appointment}
    notification_id = create_notification(business_id, "email", payload)

    subject = "New inspection booked (AI Receptionist)"
    body = "\n".join(
        [
            "A new inspection/viewing was booked by the AI receptionist.",
            "",
            f"Lead ID: {appointment.get('lead_id') or appointment.get('leadId') or ''}",
            f"Scheduled For: {appointment.get('scheduled_for') or appointment.get('scheduledFor') or ''}",
            f"Location: {appointment.get('location') or ''}",
            "",
            f"Raw: {_json_dump(appointment)}",
        ]
    )

    try:
        send_email(subject, body)
        if notification_id:
            mark_notification_status(notification_id, "sent")
    except Exception as e:
        if notification_id:
            mark_notification_status(
                notification_id,
                "failed",
                {"type": "appointment_booked", "error": str(e), "appointment": appointment},
            )

