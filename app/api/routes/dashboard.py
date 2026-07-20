from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_business_id, require_dashboard_api_key
from app.integrations.supabase_client import get_supabase_admin

router = APIRouter(prefix="/dashboard")


def _normalize_cursor(value: str) -> str:
    normalized = value.strip()
    if " " in normalized and "+" not in normalized:
        normalized = normalized.replace(" ", "+")
    if normalized.endswith("+00:00"):
        normalized = normalized[:-6] + "Z"
    return normalized


def _cursor_from_last(items: list[dict[str, Any]], field: str) -> str | None:
    if not items:
        return None
    value = items[-1].get(field)
    if isinstance(value, str) and value:
        return _normalize_cursor(value)
    return None


@router.get("/live")
def get_live(
    business_id: str = Depends(get_business_id),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    resp = (
        db.table("calls")
        .select("id,vapi_call_id,status,from_phone,to_phone,started_at,ended_at,created_at,updated_at")
        .eq("business_id", business_id)
        .in_("status", ["ringing", "in_progress"])
        .order("updated_at", desc=True)
        .limit(25)
        .execute()
    )
    calls = getattr(resp, "data", []) or []
    return {"calls": calls}


@router.get("/calls")
def list_calls(
    business_id: str = Depends(get_business_id),
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    query = (
        db.table("calls")
        .select("id,vapi_call_id,status,from_phone,to_phone,started_at,ended_at,created_at,updated_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    if cursor:
        query = query.lt("created_at", _normalize_cursor(cursor))
    resp = query.execute()
    calls = getattr(resp, "data", []) or []
    return {"calls": calls, "nextCursor": _cursor_from_last(calls, "created_at")}


@router.get("/leads")
def list_leads(
    business_id: str = Depends(get_business_id),
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    query = (
        db.table("leads")
        .select("id,full_name,phone,email,intent,property_type,location_interest,budget_text,status,notes,created_at,updated_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    if cursor:
        query = query.lt("created_at", _normalize_cursor(cursor))
    resp = query.execute()
    leads = getattr(resp, "data", []) or []
    return {"leads": leads, "nextCursor": _cursor_from_last(leads, "created_at")}


@router.get("/appointments")
def list_appointments(
    business_id: str = Depends(get_business_id),
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    upcomingOnly: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    query = (
        db.table("appointments")
        .select("id,lead_id,scheduled_for,location,status,metadata,created_at,updated_at")
        .eq("business_id", business_id)
        .order("scheduled_for", desc=False)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    if upcomingOnly:
        now_iso = datetime.now(timezone.utc).isoformat()
        query = query.gte("scheduled_for", now_iso)
    if cursor:
        query = query.gt("scheduled_for", _normalize_cursor(cursor))
    resp = query.execute()
    appointments = getattr(resp, "data", []) or []
    return {"appointments": appointments, "nextCursor": _cursor_from_last(appointments, "scheduled_for")}


@router.get("/call-summaries")
def list_call_summaries(
    business_id: str = Depends(get_business_id),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    query = (
        db.table("call_summaries")
        .select("id,call_id,summary,extracted_fields,created_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if cursor:
        query = query.lt("created_at", _normalize_cursor(cursor))
    resp = query.execute()
    summaries = getattr(resp, "data", []) or []
    return {"callSummaries": summaries, "nextCursor": _cursor_from_last(summaries, "created_at")}


@router.get("/notifications")
def list_notifications(
    business_id: str = Depends(get_business_id),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    query = (
        db.table("notifications")
        .select("id,channel,status,payload,created_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if cursor:
        query = query.lt("created_at", _normalize_cursor(cursor))
    resp = query.execute()
    notifications = getattr(resp, "data", []) or []
    return {"notifications": notifications, "nextCursor": _cursor_from_last(notifications, "created_at")}


@router.get("/business-settings")
def get_business_settings(
    business_id: str = Depends(get_business_id),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    resp = db.table("business_settings").select("business_id,hours,qualification_rules,notification_preferences,updated_at").eq("business_id", business_id).limit(1).execute()
    data = getattr(resp, "data", []) or []
    return {"businessSettings": data[0] if data else None}


@router.put("/business-settings")
def update_business_settings(
    body: dict[str, Any],
    business_id: str = Depends(get_business_id),
    _: None = Depends(require_dashboard_api_key),
):
    updates: dict[str, Any] = {}
    for key in ("hours", "qualification_rules", "notification_preferences"):
        if key in body:
            updates[key] = body[key]

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    updates["business_id"] = business_id

    db = get_supabase_admin()
    resp = db.table("business_settings").upsert(updates, on_conflict="business_id").execute()
    data = getattr(resp, "data", []) or []
    return {"businessSettings": data[0] if data else None}


@router.get("/analytics")
def get_analytics(
    business_id: str = Depends(get_business_id),
    days: int = Query(default=7, ge=1, le=30),
    _: None = Depends(require_dashboard_api_key),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.isoformat()
    db = get_supabase_admin()

    calls_resp = db.table("calls").select("id", count="exact").eq("business_id", business_id).gte("created_at", since_iso).execute()
    leads_resp = db.table("leads").select("id", count="exact").eq("business_id", business_id).gte("created_at", since_iso).execute()
    appt_resp = db.table("appointments").select("id", count="exact").eq("business_id", business_id).gte("created_at", since_iso).execute()

    return {
        "since": since_iso,
        "counts": {
            "calls": getattr(calls_resp, "count", None),
            "leads": getattr(leads_resp, "count", None),
            "appointments": getattr(appt_resp, "count", None),
        },
    }


@router.get("/home")
def get_home(
    business_id: str = Depends(get_business_id),
    days: int = Query(default=7, ge=1, le=30),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    now_iso = datetime.now(timezone.utc).isoformat()

    live_calls = (
        db.table("calls")
        .select("id,vapi_call_id,status,from_phone,to_phone,started_at,created_at,updated_at")
        .eq("business_id", business_id)
        .in_("status", ["ringing", "in_progress"])
        .order("updated_at", desc=True)
        .limit(10)
        .execute()
    )

    recent_leads = (
        db.table("leads")
        .select("id,full_name,phone,email,intent,property_type,location_interest,budget_text,status,created_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )

    upcoming_appointments = (
        db.table("appointments")
        .select("id,lead_id,scheduled_for,location,status,metadata,created_at")
        .eq("business_id", business_id)
        .gte("scheduled_for", now_iso)
        .order("scheduled_for", desc=False)
        .limit(5)
        .execute()
    )

    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_iso = since.isoformat()
    calls_resp = db.table("calls").select("id", count="exact").eq("business_id", business_id).gte("created_at", since_iso).execute()
    leads_resp = db.table("leads").select("id", count="exact").eq("business_id", business_id).gte("created_at", since_iso).execute()
    appt_resp = db.table("appointments").select("id", count="exact").eq("business_id", business_id).gte("created_at", since_iso).execute()

    return {
        "liveCalls": getattr(live_calls, "data", []) or [],
        "recentLeads": getattr(recent_leads, "data", []) or [],
        "upcomingAppointments": getattr(upcoming_appointments, "data", []) or [],
        "analytics": {
            "since": since_iso,
            "counts": {
                "calls": getattr(calls_resp, "count", None),
                "leads": getattr(leads_resp, "count", None),
                "appointments": getattr(appt_resp, "count", None),
            },
        },
    }


@router.get("/activity")
def get_activity(
    business_id: str = Depends(get_business_id),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    _: None = Depends(require_dashboard_api_key),
):
    db = get_supabase_admin()
    per_source = max(5, min(100, limit))

    leads_q = (
        db.table("leads")
        .select("id,full_name,phone,email,intent,property_type,location_interest,budget_text,status,created_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(per_source)
    )
    appts_q = (
        db.table("appointments")
        .select("id,lead_id,scheduled_for,location,status,metadata,created_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(per_source)
    )
    calls_q = (
        db.table("calls")
        .select("id,vapi_call_id,status,from_phone,to_phone,started_at,ended_at,created_at,updated_at")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(per_source)
    )

    if cursor:
        normalized = _normalize_cursor(cursor)
        leads_q = leads_q.lt("created_at", normalized)
        appts_q = appts_q.lt("created_at", normalized)
        calls_q = calls_q.lt("created_at", normalized)

    leads_resp = leads_q.execute()
    appts_resp = appts_q.execute()
    calls_resp = calls_q.execute()

    leads = getattr(leads_resp, "data", []) or []
    appts = getattr(appts_resp, "data", []) or []
    calls = getattr(calls_resp, "data", []) or []

    events: list[dict[str, Any]] = []

    for lead in leads or []:
        ts = lead.get("created_at")
        events.append({"type": "lead_created", "timestamp": _normalize_cursor(ts) if isinstance(ts, str) else ts, "lead": lead})

    for appt in appts or []:
        ts = appt.get("created_at")
        events.append(
            {"type": "appointment_scheduled", "timestamp": _normalize_cursor(ts) if isinstance(ts, str) else ts, "appointment": appt}
        )

    for call in calls or []:
        ts = call.get("created_at")
        call_status = call.get("status")
        if call_status == "ended":
            events.append({"type": "call_ended", "timestamp": _normalize_cursor(ts) if isinstance(ts, str) else ts, "call": call})
        else:
            events.append({"type": "call_started", "timestamp": _normalize_cursor(ts) if isinstance(ts, str) else ts, "call": call})

    def _ts_value(item: dict[str, Any]) -> str:
        value = item.get("timestamp")
        return value if isinstance(value, str) else ""

    events = [e for e in events if _ts_value(e)]
    events.sort(key=_ts_value, reverse=True)
    events = events[:limit]

    next_cursor = events[-1]["timestamp"] if events else None
    return {"events": events, "nextCursor": _normalize_cursor(next_cursor) if isinstance(next_cursor, str) else next_cursor}
