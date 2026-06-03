"""WebSocket /ws/{conversation_id} — 流式对话。

支持通过 LLM 输出的控制标签实时驱动 Live2D 数字人表情：
- [emotion:idle|think|happy|sad]
- [expression:mmy|lks|wh|anya|anya2|W]

标签会在流式过程中被提取：
  - 发出 type=live2d.emotion 结构化事件（前端实时驱动）
  - 对应的 token 内容会被清理，不下发标签文字
"""

import re
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage

from asukabot.core.graph.dispatch import build_agent

router = APIRouter()

# 表情控制标签正则（支持大小写，表情名允许常见字符）
EMOTION_RE = re.compile(r"\[emotion:(idle|think|happy|sad)\]", re.IGNORECASE)
EXPRESSION_RE = re.compile(r"\[expression:([A-Za-z0-9_. -]+)\]", re.IGNORECASE)


class Live2DTagExtractor:
    """增量处理流式文本，提取完整控制标签并返回干净文字 + 事件。"""

    # 控制标签的开头（小写），用于判断流式分片是否截断在半个标签里。
    _TAG_OPENERS = ("[emotion:", "[expression:")

    def __init__(self) -> None:
        self.buffer = ""

    @classmethod
    def _maybe_incomplete_tag(cls, rest: str) -> bool:
        """rest 以 '[' 开头但未匹配成完整标签时，判断它是否可能是被流式分片
        截断的标签（仍在累积中），是则应继续缓冲等待后续字符，而不是把 '[' 当普通字符吐出。

        例：'[' / '[exp'（标签开头的前缀，仍在生长）→ True；
            '[expression:ku'（已有完整开头但 ']' 还没到）→ True；
            '[1]' / '[abc'（不可能是控制标签）→ False。
        """
        low = rest.lower()
        for opener in cls._TAG_OPENERS:
            # rest 是某个 opener 的前缀（标签开头被截断，仍可能补全）
            if opener.startswith(low):
                return True
            # rest 已包含完整 opener，但闭合 ']' 尚未到达
            if low.startswith(opener):
                return True
        return False

    def feed(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        if not text:
            return "", []

        self.buffer += text
        events: list[dict[str, Any]] = []
        output_parts: list[str] = []
        i = 0

        while i < len(self.buffer):
            # 寻找下一个可能的标签起始
            tag_start = self.buffer.find("[", i)
            if tag_start == -1:
                output_parts.append(self.buffer[i:])
                i = len(self.buffer)
                break

            # 把 [ 之前的干净文字收集
            if tag_start > i:
                output_parts.append(self.buffer[i:tag_start])

            # 从这里尝试匹配完整标签
            emo_match = EMOTION_RE.match(self.buffer, tag_start)
            exp_match = EXPRESSION_RE.match(self.buffer, tag_start)

            matched = None
            if emo_match and emo_match.start() == tag_start:
                matched = emo_match
            elif exp_match and exp_match.start() == tag_start:
                matched = exp_match

            if matched:
                # 完整标签，生成事件
                if matched.re is EMOTION_RE:
                    emotion = matched.group(1).lower()
                    events.append({"type": "live2d.emotion", "emotion": emotion})
                else:
                    expression = matched.group(1).strip()
                    events.append({"type": "live2d.emotion", "expression": expression})

                i = matched.end()
                continue
            else:
                # 不是完整标签：若可能是被分片截断的标签开头，则保留到下次再判断；
                # 否则把这个 '[' 当普通字符输出。
                rest = self.buffer[tag_start:]
                if self._maybe_incomplete_tag(rest):
                    # 跨 chunk 的半个标签：把已输出的干净文字留下，buffer 从 '[' 起保留
                    i = tag_start
                    break
                output_parts.append("[")
                i = tag_start + 1
                continue

        # 未处理完的部分（可能包含部分标签或后续文字）保留在 buffer
        self.buffer = self.buffer[i:]
        clean_text = "".join(output_parts)
        return clean_text, events

    def flush(self) -> str:
        """结束时把剩余干净文字吐出。"""
        remaining = self.buffer
        self.buffer = ""
        return remaining


@router.websocket("/ws/{conversation_id}")
async def ws_chat(websocket: WebSocket, conversation_id: str) -> None:
    """每条客户端消息触发一轮流式回复。

    客户端发送：{"message": "..."}
    服务端推送：
      {"type": "token", "content": "..."}          增量（已清理标签）
      {"type": "live2d.emotion", ...}             实时表情/情绪指令（可选）
      {"type": "done"}                            结束
      {"type": "error", "content": "..."}         异常

    LLM 可以在文字中输出 [emotion:...] / [expression:...] 控制数字人表演。
    后端会实时提取标签并发出结构化事件，同时保证下发的 token 干净。
    """
    await websocket.accept()
    agent = await build_agent()
    config = {"configurable": {"thread_id": conversation_id}}

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            if not message:
                continue

            extractor = Live2DTagExtractor()

            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                version="v2",
            ):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = chunk.content
                    if content and isinstance(content, str):
                        clean, evts = extractor.feed(content)
                        for evt in evts:
                            await websocket.send_json(evt)
                        if clean:
                            await websocket.send_json(
                                {"type": "token", "content": clean}
                            )

            # 结束时 flush 剩余干净文字（理论上不应有未闭合标签）
            remaining = extractor.flush()
            if remaining:
                await websocket.send_json({"type": "token", "content": remaining})

            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "content": str(exc)})
