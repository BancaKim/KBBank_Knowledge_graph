import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import get_db_optional
from knowledge_graph.db import Neo4jConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] | None = Field(None, max_length=20)


class ChatResponse(BaseModel):
    answer: str
    referenced_nodes: list[dict]
    elapsed_seconds: float = 0.0


@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: Neo4jConnection | None = Depends(get_db_optional),
    x_openai_key: str | None = Header(None, alias="X-OpenAI-Key"),
):
    """Process a chat message using GraphRAG."""
    import time

    api_key = x_openai_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API 키가 설정되지 않았습니다. 클라이언트에서 API 키를 입력하거나 서버 환경변수를 설정해주세요.",
        )

    try:
        if db is None:
            return ChatResponse(
                answer="현재 Neo4j 데이터베이스가 연결되지 않아 챗봇 기능을 사용할 수 없습니다. 그래프 시각화와 상품 검색은 정상적으로 이용 가능합니다.",
                referenced_nodes=[],
            )
        import asyncio
        from backend.chatbot import chat

        start = time.monotonic()
        result = await asyncio.to_thread(chat, request.message, request.history, db, api_key=x_openai_key)
        elapsed = round(time.monotonic() - start, 2)
        return ChatResponse(**result, elapsed_seconds=elapsed)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Chat error")
        raise HTTPException(
            status_code=500,
            detail="답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc
