"""
Integrity report generation endpoint.

Accepts a session's raw proctoring events and returns a mentor-facing
LLM-generated report. Uses the globally configured OpenAI API key.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.settings import settings
from api.config import openai_plan_to_model_name
import openai


router = APIRouter()


class GenerateReportRequest(BaseModel):
    session_uuid: str
    user_id: int
    events: List[Dict[str, Any]]


def _summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds quick aggregate stats and a compact timeline for the prompt."""
    if not events:
        return {
            "count": 0,
            "by_severity": {},
            "by_type": {},
            "timeline": [],
            "start": None,
            "end": None,
        }

    # Normalize timestamps and fields defensively
    normalized = []
    for e in events:
        ts_raw = e.get("timestamp")
        ts: Optional[datetime] = None
        if isinstance(ts_raw, (int, float)):
            # unix ms or s – assume ms if very large
            ts = datetime.fromtimestamp(ts_raw / 1000.0 if ts_raw > 1e12 else ts_raw)
        elif isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                ts = None

        normalized.append(
            {
                "type": e.get("type") or e.get("event_type") or "unknown",
                "severity": (e.get("severity") or "unknown").lower(),
                "timestamp": ts,
                "flagged": bool(e.get("flagged", False)),
                "data": e.get("data") or {},
            }
        )

    normalized.sort(key=lambda x: x["timestamp"] or datetime.min)

    by_severity: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    timeline: List[str] = []
    start, end = None, None

    for e in normalized:
        by_severity[e["severity"]] = by_severity.get(e["severity"], 0) + 1
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        if e["timestamp"]:
            if start is None:
                start = e["timestamp"]
            end = e["timestamp"]
            timeline.append(
                f"{e['timestamp'].isoformat()} | {e['type']} | severity={e['severity']} | flagged={e['flagged']}"
            )
        else:
            timeline.append(
                f"unknown-time | {e['type']} | severity={e['severity']} | flagged={e['flagged']}"
            )

    return {
        "count": len(normalized),
        "by_severity": by_severity,
        "by_type": by_type,
        "timeline": timeline,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }


def _build_system_prompt() -> str:
    return (
        "You are an assessment integrity reviewer assistant. "
        "Given raw proctoring events for a single session, you must synthesize a concise, mentor-facing report. "
        "Use severity and timing to infer risk. "
        "If evidence is weak or ambiguous, state that clearly. "
        "Never fabricate events that are not present. "
        "Prefer actionable recommendations over generic advice. "
        "Return a clean, readable markdown report with these sections: \n"
        "1) Summary (2-4 sentences).\n"
        "2) Timeline Highlights (key moments with time and reason).\n"
        "3) Risk Assessment (0-100) with justification.\n"
        "4) Mentor Suggestions (bullet points tailored to the observed events).\n"
        "5) Event Statistics (counts by type and severity)."
    )


@router.post("/report")
async def generate_integrity_report(request: GenerateReportRequest) -> Dict[str, str]:
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key is not configured on the server")

    aggregates = _summarize_events(request.events)

    # Build user-visible content compactly to reduce token usage
    user_prompt = {
        "session_uuid": request.session_uuid,
        "user_id": request.user_id,
        "summary": {
            "total_events": aggregates["count"],
            "by_severity": aggregates["by_severity"],
            "by_type": aggregates["by_type"],
            "start": aggregates["start"],
            "end": aggregates["end"],
        },
        "timeline": aggregates["timeline"][:400],  # cap to keep prompt bounded
    }

    model = openai_plan_to_model_name.get("text-mini") or "gpt-4.1-mini"
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        completion = await client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {
                    "role": "user",
                    "content": (
                        "Generate a mentor-facing integrity report based on this JSON input.\n"
                        "JSON:\n" + str(user_prompt)
                    ),
                },
            ],
        )
        content = completion.choices[0].message.content or ""
        return {"report": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


