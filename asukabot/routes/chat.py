"""POST /chat — 非流式对话接口（调试用）。"""

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from asukabot.core.graph.dispatch import build_agent

router = APIRouter()


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """同步调用 Agent，返回完整回复。"""
    agent = await build_agent()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=req.message)]},
        config={"configurable": {"thread_id": req.conversation_id}},
    )
    reply = result["messages"][-1].content
    return ChatResponse(reply=reply)
