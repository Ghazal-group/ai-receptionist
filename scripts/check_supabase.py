from pathlib import Path

from dotenv import dotenv_values
from supabase import create_client


def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    cfg = dotenv_values(env_path)

    url = cfg.get("SUPABASE_URL")
    key = cfg.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in backend/.env")

    client = create_client(url, key)
    latest_lead = (
        client.table("leads")
        .select("id,full_name,phone,created_at")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    print({"latestLead": latest_lead.data})

    latest_call = (
        client.table("calls")
        .select("id,vapi_call_id,status,created_at")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    print({"latestCall": latest_call.data})

    latest_summary = (
        client.table("call_summaries")
        .select("id,call_id,created_at,extracted_fields")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    print({"latestCallSummary": latest_summary.data})

    latest_appointment = (
        client.table("appointments")
        .select("id,lead_id,scheduled_for,status,created_at,metadata")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    print({"latestAppointment": latest_appointment.data})


if __name__ == "__main__":
    main()
