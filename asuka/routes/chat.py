"""POST /chat — 非流式对话接口（调试用）。"""

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from asuka.core.graph.dispatch import build_agent
from asuka.routes.ws import Live2DTagExtractor  # reuse for tag stripping

router = APIRouter()


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """同步调用 Agent，返回完整回复（自动剥离表情控制标签）。"""
    agent = await build_agent()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=req.message)]},
        config={"configurable": {"thread_id": req.conversation_id}},
    )
    reply = result["messages"][-1].content
    # 剥离 [emotion:...]/[expression:...] 标签，保持与 WS 流式一致
    extractor = Live2DTagExtractor()
    clean_reply, _ = extractor.feed(str(reply))
    clean_reply = extractor.flush() or clean_reply  # 确保 flush
    return ChatResponse(reply=clean_reply)
