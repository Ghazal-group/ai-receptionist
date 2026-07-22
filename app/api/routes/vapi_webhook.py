import json
import os
import re
import time
import urllib.request
import uuid
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.core.config import settings
from app.integrations.supabase_client import get_supabase_admin
from app.services.calcom_service import create_booking_for_appointment
from app.services.notification_service import notify_owner_appointment_booked, notify_owner_lead_created


router = APIRouter(prefix="/webhooks")

# #region debug-point A:init
_DBG_ENV_PATH = os.path.join(".dbg", "appointment-not-booking.env")
_DBG_URL_DEFAULT = "http://127.0.0.1:7777/event"
_DBG_SESSION_DEFAULT = "appointment-not-booking"


def _dbg(hypothesis_id: str, msg: str, data: dict[str, Any] | None = None, trace_id: str | None = None) -> None:
    try:
        url = _DBG_URL_DEFAULT
        session_id = _DBG_SESSION_DEFAULT
        try:
            with open(_DBG_ENV_PATH, "r", encoding="utf-8") as f:
                content = f.read().splitlines()
            for line in content:
                if line.startswith("DEBUG_SERVER_URL="):
                    url = line.split("=", 1)[1].strip() or url
                elif line.startswith("DEBUG_SESSION_ID="):
                    session_id = line.split("=", 1)[1].strip() or session_id
        except Exception:
            pass

        payload = {
            "sessionId": session_id,
            "runId": "pre",
            "hypothesisId": hypothesis_id,
            "location": "backend/app/api/routes/vapi_webhook.py",
            "msg": msg,
            "data": data or {},
            "traceId": trace_id,
            "ts": int(time.time() * 1000),
        }
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=1.5,
        ).read()
    except Exception:
        return


# #endregion


def _resolve_business_id(message: dict[str, Any]) -> str | None:
    call = message.get("call") or {}
    metadata = call.get("metadata") or {}

    business_id = metadata.get("businessId") or metadata.get("business_id")
    if business_id:
        return str(business_id)
    if settings.default_business_id:
        return str(settings.default_business_id)
    return None


def _safe_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0).isoformat()
    return None


def _normalize_call_status(raw: Any) -> str:
    if raw is None:
        return "unknown"
    value = str(raw).strip()
    if not value:
        return "unknown"
    value = value.replace("-", "_").lower()
    mapping = {
        "started": "in_progress",
        "inprogress": "in_progress",
        "in_progress": "in_progress",
        "ringing": "ringing",
        "queued": "queued",
        "ended": "ended",
        "completed": "ended",
        "complete": "ended",
        "failed": "failed",
        "error": "failed",
    }
    normalized = mapping.get(value, value)
    if normalized not in {"queued", "ringing", "in_progress", "ended", "failed", "unknown"}:
        return "unknown"
    return normalized


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        text = raw.lower()
        lagos_tz = timezone(timedelta(hours=1))
        now = datetime.now(lagos_tz)
        base_date = None
        if "tomorrow" in text:
            base_date = now.date() + timedelta(days=1)
        elif "today" in text:
            base_date = now.date()
        if base_date is None:
            return None
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        dt = datetime(
            base_date.year,
            base_date.month,
            base_date.day,
            hour,
            minute,
            tzinfo=lagos_tz,
        )
        return dt.astimezone(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_summary_from_analysis(analysis: Any) -> str | None:
    if not isinstance(analysis, dict):
        return None
    direct = analysis.get("summary")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for value in analysis.values():
        if not isinstance(value, dict):
            continue
        name = value.get("name")
        result = value.get("result")
        if isinstance(name, str) and "analysis.summary" in name and isinstance(result, str) and result.strip():
            return result.strip()
    return None


def _extract_tool_call(tool_call: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any]]:
    tool_call_id = tool_call.get("id") or tool_call.get("toolCallId")

    tool_name = tool_call.get("name")
    params: Any = tool_call.get("parameters")

    if not tool_name or params is None:
        function_obj = tool_call.get("function") or tool_call.get("tool") or {}
        if isinstance(function_obj, dict):
            if not tool_name:
                maybe_name = function_obj.get("name")
                if isinstance(maybe_name, str) and maybe_name:
                    tool_name = maybe_name

            if params is None:
                args = (
                    function_obj.get("arguments")
                    or function_obj.get("args")
                    or tool_call.get("arguments")
                    or tool_call.get("args")
                )
                if isinstance(args, dict):
                    params = args
                elif isinstance(args, str) and args.strip():
                    try:
                        parsed = json.loads(args)
                        if isinstance(parsed, dict):
                            params = parsed
                    except Exception:
                        params = None

    if not isinstance(params, dict):
        params = {}

    return tool_call_id, tool_name, params


def _get_call_row_id(business_id: str, vapi_call_id: str) -> str | None:
    db = get_supabase_admin()
    resp = (
        db.table("calls")
        .select("id")
        .eq("business_id", business_id)
        .eq("vapi_call_id", vapi_call_id)
        .limit(1)
        .execute()
    )
    if getattr(resp, "data", None) and len(resp.data) > 0:
        return resp.data[0].get("id")
    return None


def _upsert_call_row(payload: dict[str, Any]) -> str | None:
    business_id = payload.get("business_id")
    vapi_call_id = payload.get("vapi_call_id")

    if not business_id:
        return None

    db = get_supabase_admin()

    if vapi_call_id:
        existing_id = _get_call_row_id(str(business_id), str(vapi_call_id))
        if existing_id:
            db.table("calls").update(payload).eq("id", existing_id).execute()
            return existing_id

    resp = db.table("calls").insert(payload).execute()
    if getattr(resp, "data", None) and len(resp.data) > 0:
        return resp.data[0].get("id")
    return None


@router.post("/vapi")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_vapi_secret: str | None = Header(default=None, convert_underscores=False),
    x_vapi_secret_alt: str | None = Header(default=None, alias="X-Vapi-Secret"),
):
    trace_id = str(uuid.uuid4())
    if settings.vapi_webhook_secret:
        if request.client and request.client.host in ("127.0.0.1", "::1"):
            pass
        else:
            provided = x_vapi_secret or x_vapi_secret_alt
            if provided != settings.vapi_webhook_secret:
                raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    message: dict[str, Any] = {}
    if isinstance(body, dict):
        raw_message = body.get("message")
        if isinstance(raw_message, dict):
            message = raw_message
        else:
            message = body

    message_type = message.get("type") or "unknown"

    business_id = _resolve_business_id(message)
    call = message.get("call") or {}
    vapi_call_id = call.get("id") or call.get("callId") or call.get("vapiCallId")
    _dbg("A", "webhook_received", {"message_type": message_type, "business_id": business_id, "vapi_call_id": vapi_call_id}, trace_id=trace_id)

    if message_type in ("status-update", "end-of-call-report", "speech-update", "conversation-update"):
        call_row_id: str | None = None
        if business_id and vapi_call_id:
            resolved_status = message.get("status") or call.get("status")
            if not resolved_status and message_type in ("speech-update", "conversation-update"):
                resolved_status = "in_progress"
            if not resolved_status and message_type == "end-of-call-report":
                resolved_status = "ended"
            payload = {
                "business_id": business_id,
                "vapi_call_id": str(vapi_call_id),
                "status": _normalize_call_status(resolved_status),
                "from_phone": call.get("customer", {}).get("number") or call.get("from"),
                "to_phone": call.get("phoneNumber", {}).get("number") or call.get("to"),
                "started_at": _safe_dt(call.get("startedAt")),
                "ended_at": _safe_dt(call.get("endedAt")),
                "raw_event": message,
            }
            call_row_id = _upsert_call_row(payload)

        if message_type == "end-of-call-report" and business_id and vapi_call_id and call_row_id:
            artifact = message.get("artifact") or {}
            transcript = artifact.get("transcript")
            analysis = message.get("analysis") or {}
            analysis_summary = _extract_summary_from_analysis(analysis)
            transcript_text = transcript.strip() if isinstance(transcript, str) and transcript.strip() else None
            artifact_summary = artifact.get("summary")
            vapi_summary = analysis_summary or (artifact_summary.strip() if isinstance(artifact_summary, str) else None)
            stored_text = transcript_text or vapi_summary

            extracted = {
                "endedReason": message.get("endedReason"),
                "summaryStatus": "stored_transcript" if transcript_text else "stored_vapi",
                "summarySource": "transcript" if transcript_text else "vapi",
                "vapiSummary": vapi_summary,
                "hasTranscript": bool(transcript_text),
            }

            db = get_supabase_admin()
            db.table("call_summaries").upsert(
                {
                    "business_id": business_id,
                    "call_id": call_row_id,
                    "summary": stored_text,
                    "extracted_fields": extracted,
                },
                on_conflict="call_id",
            ).execute()

        return {"ok": True}

    if message_type == "tool-calls":
        tool_call_list = message.get("toolCallList") or message.get("toolCalls") or []
        results: list[dict[str, Any]] = []

        tool_names: list[str | None] = []
        for tc in tool_call_list:
            _, name, _ = _extract_tool_call(tc)
            tool_names.append(name)

        for tool_call in tool_call_list:
            tool_call_id, tool_name, params = _extract_tool_call(tool_call)

            result_text = "ok"

            if business_id:
                db = get_supabase_admin()

                try:
                    if tool_name in ("upsertLead", "createLead"):
                        lead_payload = {
                            "business_id": business_id,
                            "call_id": None,
                            "full_name": params.get("fullName") or params.get("name"),
                            "phone": params.get("phone"),
                            "email": params.get("email"),
                            "intent": params.get("intent"),
                            "property_type": params.get("propertyType"),
                            "location_interest": params.get("locationInterest"),
                            "budget_text": params.get("budget"),
                            "timeframe": params.get("timeframe"),
                            "status": params.get("status") or "new",
                            "notes": params.get("notes"),
                        }
                        resp = db.table("leads").insert(lead_payload).execute()
                        lead_id = None
                        if getattr(resp, "data", None) and len(resp.data) > 0:
                            lead_id = resp.data[0].get("id")
                        result_text = json.dumps({"status": "created", "leadId": lead_id})
                        if getattr(resp, "data", None) and len(resp.data) > 0:
                            background_tasks.add_task(notify_owner_lead_created, business_id, resp.data[0])

                    elif tool_name in ("createAppointment", "bookAppointment"):
                        scheduled_for_raw = params.get("scheduledFor") or params.get("scheduled_for")
                        scheduled_for_dt = _parse_iso_datetime(scheduled_for_raw)
                        now_utc = datetime.now(timezone.utc)
                        scheduled_for = scheduled_for_dt.isoformat() if scheduled_for_dt else None
                        lead_id = params.get("leadId") or params.get("lead_id")
                        caller_phone = (
                            (call.get("customer") or {}).get("number")
                            or call.get("from")
                            or (call.get("customer") or {}).get("phone")
                        )
                        _dbg(
                            "H1",
                            "bookAppointment_received",
                            {
                                "toolCallId": tool_call_id,
                                "scheduledFor_raw": scheduled_for_raw,
                                "scheduledFor_parsed": scheduled_for,
                                "now_utc": now_utc.isoformat(),
                                "leadId_incoming": lead_id,
                                "caller_phone": caller_phone,
                            },
                            trace_id=trace_id,
                        )
                        if not lead_id and caller_phone:
                            existing = (
                                db.table("leads")
                                .select("id")
                                .eq("business_id", business_id)
                                .eq("phone", caller_phone)
                                .order("created_at", desc=True)
                                .limit(1)
                                .execute()
                            )
                            if getattr(existing, "data", None) and len(existing.data) > 0:
                                lead_id = existing.data[0].get("id")
                            else:
                                created = (
                                    db.table("leads")
                                    .insert(
                                        {
                                            "business_id": business_id,
                                            "call_id": None,
                                            "full_name": params.get("fullName") or params.get("name") or "Unknown Caller",
                                            "phone": caller_phone,
                                            "status": "new",
                                        }
                                    )
                                    .execute()
                                )
                                if getattr(created, "data", None) and len(created.data) > 0:
                                    lead_id = created.data[0].get("id")
                        _dbg(
                            "H3",
                            "bookAppointment_lead_resolved",
                            {
                                "toolCallId": tool_call_id,
                                "leadId_resolved": lead_id,
                                "leadId_present": bool(lead_id),
                                "scheduledFor_present": bool(scheduled_for),
                                "scheduledFor_in_future": bool(scheduled_for_dt and scheduled_for_dt >= now_utc),
                            },
                            trace_id=trace_id,
                        )

                        if not lead_id or not scheduled_for_dt or scheduled_for_dt < now_utc:
                            result_text = json.dumps(
                                {
                                    "status": "failed",
                                    "error": "scheduledFor must be a future ISO datetime and leadId must be resolved",
                                    "leadId_present": bool(lead_id),
                                    "scheduledFor_present": bool(scheduled_for),
                                    "scheduledFor_in_future": bool(scheduled_for_dt and scheduled_for_dt >= now_utc),
                                    "scheduledFor_raw": scheduled_for_raw,
                                    "caller_phone": caller_phone,
                                }
                            )
                            results.append({"name": tool_name, "toolCallId": tool_call_id, "result": result_text})
                            continue

                        appointment_payload = {
                            "business_id": business_id,
                            "lead_id": lead_id,
                            "scheduled_for": scheduled_for,
                            "location": params.get("location"),
                            "status": "scheduled",
                            "metadata": params.get("metadata") or {},
                        }
                        resp = db.table("appointments").insert(appointment_payload).execute()
                        appt_id = None
                        if getattr(resp, "data", None) and len(resp.data) > 0:
                            appt_id = resp.data[0].get("id")
                        result_text = json.dumps({"status": "scheduled", "appointmentId": appt_id})
                        if getattr(resp, "data", None) and len(resp.data) > 0:
                            background_tasks.add_task(notify_owner_appointment_booked, business_id, resp.data[0])
                            if appt_id:
                                background_tasks.add_task(create_booking_for_appointment, business_id, appt_id)

                    elif tool_name in ("lookupFaq", "lookupFAQ", "faqLookup"):
                        query = (params.get("query") or "").strip()
                        if query:
                            resp = (
                                db.table("faqs")
                                .select("question,answer")
                                .eq("business_id", business_id)
                                .eq("is_active", True)
                                .ilike("question", f"%{query}%")
                                .limit(1)
                                .execute()
                            )
                            if getattr(resp, "data", None) and len(resp.data) > 0:
                                result_text = resp.data[0].get("answer") or ""
                            else:
                                result_text = ""
                        else:
                            result_text = ""

                    elif tool_name in ("updateLead", "qualifyLead"):
                        lead_id = params.get("leadId") or params.get("lead_id")
                        updates: dict[str, Any] = {}
                        if params.get("status"):
                            updates["status"] = params.get("status")
                        if params.get("notes"):
                            updates["notes"] = params.get("notes")
                        if lead_id and updates:
                            db.table("leads").update(updates).eq("id", lead_id).eq("business_id", business_id).execute()
                            result_text = "updated"
                        else:
                            result_text = "skipped"
                except Exception as e:
                    result_text = json.dumps({"status": "failed", "error": str(e)})

            results.append({"name": tool_name, "toolCallId": tool_call_id, "result": result_text})

        return {"results": results}

    return {"ok": True}
