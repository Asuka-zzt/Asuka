"""WebSocket /ws/{conversation_id} — 流式对话。"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage

from asukabot.core.graph.dispatch import build_agent

router = APIRouter()


@router.websocket("/ws/{conversation_id}")
async def ws_chat(websocket: WebSocket, conversation_id: str) -> None:
    """每条客户端消息触发一轮流式回复。

    客户端发送：{"message": "..."}
    服务端推送：{"type": "token", "content": "..."} 增量
              {"type": "done"}                    结束
              {"type": "error", "content": "..."} 异常
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

            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                version="v2",
            ):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        await websocket.send_json(
                            {"type": "token", "content": chunk.content}
                        )

            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "content": str(exc)})
