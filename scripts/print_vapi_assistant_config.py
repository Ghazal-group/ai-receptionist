import json
from pathlib import Path


def main() -> None:
    template_path = Path(__file__).resolve().parents[1] / "vapi" / "assistant.template.json"
    raw = template_path.read_text(encoding="utf-8")

    server_url = input("Enter your public SERVER_URL (e.g. https://xxxx.ngrok.app): ").strip().rstrip("/")
    rendered = raw.replace("{{SERVER_URL}}", server_url)

    parsed = json.loads(rendered)
    print(json.dumps(parsed, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

