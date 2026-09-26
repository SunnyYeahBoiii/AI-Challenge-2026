"""Claude tool-use loop that fills Candidates for the shared TRAKE board."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import anthropic

from app.config import Config
from app.services import cloud_api_client
from app.services.agent.tools import HANDLERS, TOOLS, AgentContext

logger = logging.getLogger(__name__)

MAX_TOKENS = 8000
RESULT_LOG_CHARS = 300

SYSTEM_PROMPT = """\
Bạn là agent tìm moment cho bài TRAKE của hệ thống FrameSeeker (video tin tức/giao thông Việt Nam).
Mỗi Event là một khoảnh khắc cần tìm; mọi Event của một bài phải nằm trong CÙNG MỘT video (Target Video), theo đúng thứ tự Event.

Cách làm:
1. Đọc danh sách Event. Viết truy vấn thị giác cụ thể (tiếng Anh) cho `search_moments`; khi có chữ trên màn hình hoặc lời thoại thì dùng thêm OCR/ASR keyword hoặc `keyword_search`.
2. Ưu tiên tìm nhiều Event cùng lúc bằng temporal search (nhiều query, cùng video) để ra video chung.
3. Xác minh ứng viên bằng `inspect_frames` (with_images=true để nhìn ảnh, xem OCR/ASR lân cận) trước khi thêm.
4. Chỉ `add_candidate` cho frame bạn tin là đúng (tối đa vài frame mỗi Event). Không đoán; thiếu chắc chắn thì không thêm.
5. Bạn KHÔNG chọn Selection và KHÔNG nộp DRES. Người dùng sẽ quyết định.
6. Frame có timestamp bằng 0 chưa đáng tin (chưa có dữ liệu thời gian) — bỏ qua, và nêu trong báo cáo.
Kết thúc bằng báo cáo ngắn: mỗi Event đã thêm frame nào (video, frame_index) và mức chắc chắn; Event nào chưa tìm được.
"""


def _describe_board(board: dict[str, Any], only: set[str] | None) -> tuple[str, set[str]]:
    lines: list[str] = []
    ids: set[str] = set()
    for event in board.get("events", []):
        if only and event["id"] not in only:
            continue
        ids.add(event["id"])
        lines.append(f'- {event["displayLabel"]} (event_id={event["id"]}): {event["labelText"] or "(trống)"}')
    return "\n".join(lines), ids


def _clip(text: str) -> str:
    return text if len(text) <= RESULT_LOG_CHARS else text[:RESULT_LOG_CHARS] + "…"


def _run_tool(ctx: AgentContext, block: Any) -> dict[str, Any]:
    handler = HANDLERS.get(block.name)
    if handler is None:
        content: Any = json.dumps({"error": f"unknown tool {block.name}"})
        is_error = True
    else:
        try:
            content = handler(ctx, block.input)
            is_error = False
        except Exception as error:  # tool failures go back to the model, not the caller
            logger.exception("agent tool %s failed", block.name)
            content = json.dumps({"error": f"{type(error).__name__}: {error}"})
            is_error = True
    return {"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error}


def run_agent(
    instruction: str,
    event_ids: list[str] | None,
    on_step: Callable[[dict[str, Any]], None],
    client: anthropic.Anthropic | None = None,
) -> str:
    """Run the loop; returns the final report. `on_step` gets one dict per tool call."""
    board = cloud_api_client.get_board()
    board_text, valid_ids = _describe_board(board, set(event_ids or []))
    if not valid_ids:
        raise ValueError("no matching events on the board")

    ctx = AgentContext(event_ids=valid_ids)
    client = client or anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    user_text = f"Các Event cần tìm:\n{board_text}"
    if instruction.strip():
        user_text += f"\n\nGhi chú thêm của người dùng: {instruction.strip()}"
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

    for _ in range(Config.AGENT_MAX_STEPS):
        request: dict[str, Any] = {
            "model": Config.AGENT_MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "cache_control": {"type": "ephemeral"},
            "messages": messages,
        }
        response = client.messages.create(**request)
        if response.stop_reason == "refusal":
            return "Model từ chối yêu cầu."
        # Whole content back, so thinking blocks stay attached to their turn.
        messages.append({"role": "assistant", "content": response.content})
        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            text = "".join(block.text for block in response.content if block.type == "text")
            if response.stop_reason == "max_tokens":
                text += "\n(cắt do hết max_tokens)"
            return text
        results = []
        for block in calls:
            result = _run_tool(ctx, block)
            results.append(result)
            shown = result["content"] if isinstance(result["content"], str) else "[ảnh + dữ liệu]"
            on_step({"tool": block.name, "input": block.input, "result": _clip(shown)})
        messages.append({"role": "user", "content": results})
    return "Dừng: hết số bước tối đa. Kết quả đã thêm vẫn nằm trên board."
