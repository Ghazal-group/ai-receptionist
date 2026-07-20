from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.integrations.supabase_client import get_supabase_admin


def _to_utc_start(iso_value: str) -> str:
    value = iso_value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_event_target() -> dict[str, Any] | None:
    raw = (settings.calcom_event_type_id or "").strip()
    if not raw:
        return None

    if raw.isdigit():
        return {"eventTypeId": int(raw)}

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            return {"username": parts[0], "eventTypeSlug": parts[1]}
        return None

    if "/" in raw:
        parts = [p for p in raw.split("/") if p]
        if len(parts) >= 2:
            return {"username": parts[0], "eventTypeSlug": parts[1]}
        return None

    return None


def _update_appointment_metadata(appointment_id: str, updates: dict[str, Any]) -> None:
    db = get_supabase_admin()
    existing = db.table("appointments").select("metadata").eq("id", appointment_id).limit(1).execute()
    current = {}
    if getattr(existing, "data", None) and len(existing.data) > 0 and isinstance(existing.data[0].get("metadata"), dict):
        current = existing.data[0]["metadata"]

    merged = {**current, **updates}
    db.table("appointments").update({"metadata": merged}).eq("id", appointment_id).execute()


def create_booking_for_appointment(business_id: str, appointment_id: str) -> None:
    db = get_supabase_admin()
    appt_resp = (
        db.table("appointments")
        .select("id,lead_id,scheduled_for,location,metadata")
        .eq("id", appointment_id)
        .eq("business_id", business_id)
        .limit(1)
        .execute()
    )
    if not getattr(appt_resp, "data", None):
        return

    appt = appt_resp.data[0]
    lead_id = appt.get("lead_id")
    scheduled_for = appt.get("scheduled_for")
    if not lead_id or not scheduled_for:
        _update_appointment_metadata(appointment_id, {"calcomStatus": "skipped_missing_fields"})
        return

    lead_resp = (
        db.table("leads")
        .select("id,full_name,phone,email")
        .eq("id", lead_id)
        .eq("business_id", business_id)
        .limit(1)
        .execute()
    )
    if not getattr(lead_resp, "data", None):
        _update_appointment_metadata(appointment_id, {"calcomStatus": "skipped_missing_lead"})
        return

    lead = lead_resp.data[0]
    attendee_email = lead.get("email")
    if not attendee_email:
        _update_appointment_metadata(appointment_id, {"calcomStatus": "pending_email"})
        return

    if not settings.calcom_api_key:
        _update_appointment_metadata(appointment_id, {"calcomStatus": "pending_api_key"})
        return
    event_target = _get_event_target()
    if not event_target:
        _update_appointment_metadata(appointment_id, {"calcomStatus": "pending_event_type"})
        return

    start_utc = _to_utc_start(str(scheduled_for))

    payload: dict[str, Any] = {
        "start": start_utc,
        "attendee": {
            "name": lead.get("full_name") or "Caller",
            "email": attendee_email,
            "timeZone": "Africa/Lagos",
            "phoneNumber": lead.get("phone"),
            "language": "en",
        },
        "metadata": {
            "businessId": business_id,
            "appointmentId": appointment_id,
            "leadId": lead_id,
            "location": appt.get("location"),
        },
    }

    payload.update(event_target)

    headers = {
        "Authorization": f"Bearer {settings.calcom_api_key}",
        "cal-api-version": settings.calcom_api_version,
        "Content-Type": "application/json",
    }

    url = f"{settings.calcom_base_url.rstrip('/')}/v2/bookings"

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        booking = (data or {}).get("data") or {}
        _update_appointment_metadata(
            appointment_id,
            {
                "calcomStatus": "booked",
                "calcomBookingUid": booking.get("uid"),
                "calcomBookingId": booking.get("id"),
                "calcomStart": booking.get("start") or start_utc,
            },
        )
    except Exception as e:
        _update_appointment_metadata(appointment_id, {"calcomStatus": "failed", "calcomError": str(e)})
