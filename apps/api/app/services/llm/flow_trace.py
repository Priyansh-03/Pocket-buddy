"""Optional JSON trace files per LLM tool-loop layer and pass (debug / observability)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings


def _truncate(text: str | None, max_chars: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…[truncated]…"


def _messages_digest(messages: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        item: dict[str, Any] = {"role": role}
        if "name" in m and m["name"]:
            item["name"] = m["name"]
        if "tool_call_id" in m and m["tool_call_id"]:
            item["tool_call_id"] = m["tool_call_id"]
        if "content" in m and m["content"] is not None:
            item["content"] = _truncate(str(m["content"]), max_chars)
        if "tool_calls" in m and m["tool_calls"]:
            tc = []
            for t in m["tool_calls"]:
                fn = (t.get("function") or {}) if isinstance(t.get("function"), dict) else {}
                tc.append(
                    {
                        "id": t.get("id"),
                        "name": fn.get("name"),
                        "arguments": _truncate(str(fn.get("arguments") or ""), min(max_chars, 4000)),
                    }
                )
            item["tool_calls"] = tc
        out.append(item)
    return out


@dataclass
class LlmFlowTrace:
    """Writes flow_layerNN.json at each layer boundary and flow_layerNN_pass_<slug>.json per sub-step."""

    run_dir: Path
    max_chars: int
    meta: dict[str, Any] = field(default_factory=dict)

    def _write(self, filename: str, payload: dict[str, Any]) -> None:
        path = self.run_dir / filename
        body = {"ts": datetime.now(timezone.utc).isoformat(), **self.meta, **payload}
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def trunc(self, text: str | None) -> str:
        return _truncate(text, self.max_chars)

    def layer_enter(
        self,
        layer: int,
        *,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        user_message_preview: str,
    ) -> None:
        """One file when the flow enters a tool-loop layer (before the completion call)."""
        fn = f"flow_layer{layer:02d}.json"
        self._write(
            fn,
            {
                "event": "layer_enter",
                "layer": layer,
                "provider": provider,
                "model": model,
                "message_count": len(messages),
                "messages": _messages_digest(messages, self.max_chars),
                "latest_user_message_preview": _truncate(user_message_preview, min(self.max_chars, 2000)),
            },
        )

    def pass_completion(
        self,
        layer: int,
        *,
        response_id: str | None,
        model: str | None,
        finish_reason: str | None,
        usage: dict[str, Any] | None,
        assistant_content: str | None,
        tool_calls: list[dict[str, Any]] | None,
    ) -> None:
        """After model returns (same layer): completion + optional tool call plan."""
        fn = f"flow_layer{layer:02d}_pass_completion.json"
        self._write(
            fn,
            {
                "event": "pass_completion",
                "layer": layer,
                "pass": "completion",
                "response_id": response_id,
                "model": model,
                "finish_reason": finish_reason,
                "usage": usage,
                "assistant_content": _truncate(assistant_content or "", self.max_chars),
                "tool_calls": tool_calls,
            },
        )

    def pass_tools(self, layer: int, *, tool_results: list[dict[str, Any]]) -> None:
        """After local tool execution for this layer."""
        fn = f"flow_layer{layer:02d}_pass_tools.json"
        self._write(
            fn,
            {
                "event": "pass_tools",
                "layer": layer,
                "pass": "tools",
                "tool_results": tool_results,
            },
        )


def maybe_create_flow_trace(
    settings: Settings,
    *,
    user_id: str,
    session_id: str | None,
    provider: str,
    model: str,
) -> LlmFlowTrace | None:
    raw = (settings.llm_flow_trace_dir or "").strip()
    if not raw:
        return None
    base = Path(raw).expanduser()
    if not base.is_absolute():
        api_root = Path(__file__).resolve().parents[3]
        base = (api_root / raw).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:10]
    run_dir = base / user_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    max_chars = int(settings.llm_flow_trace_max_chars or 6000)
    meta = {
        "trace_run_id": run_id,
        "user_id": user_id,
        "session_id": session_id,
        "provider": provider,
        "model": model,
    }
    trace = LlmFlowTrace(run_dir=run_dir, max_chars=max(500, max_chars), meta=meta)
    trace._write(
        "flow_run.json",
        {
            "event": "run_start",
            "run_dir": str(run_dir),
            "naming": {
                "layer_file": "flow_layerNN.json — state when entering layer NN",
                "pass_files": "flow_layerNN_pass_completion.json, flow_layerNN_pass_tools.json",
            },
        },
    )
    return trace
