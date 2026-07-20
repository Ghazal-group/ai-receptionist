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
    resp = client.table("notifications").select("id,channel,status,created_at,payload").order("created_at", desc=True).limit(3).execute()
    print(resp.data)


if __name__ == "__main__":
    main()

