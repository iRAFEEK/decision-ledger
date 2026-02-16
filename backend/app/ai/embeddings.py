import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"


async def _call_voyage(text: str, input_type: str) -> list[float]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                VOYAGE_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.voyage_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "voyage-3",
                    "input": [text],
                    "input_type": input_type,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as exc:
        log.error("voyage_embedding_error", error=str(exc), input_type=input_type)
        return []


async def generate_embedding(text: str) -> list[float]:
    return await _call_voyage(text, input_type="document")


async def generate_query_embedding(query: str) -> list[float]:
    return await _call_voyage(query, input_type="query")
