"""Phase 0 capture server. Run: uvicorn server:app --port 8765"""
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request

LOG = Path(__file__).parent / "events.jsonl"
app = FastAPI()


@app.post("/observe")
async def observe(req: Request):
    """Append one JSON event to events.jsonl with a server-side recorded_at timestamp."""
    event = await req.json()
    event["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"{event['recorded_at']} {event.get('agent')} {event.get('event')} {event.get('tool') or ''}")
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}