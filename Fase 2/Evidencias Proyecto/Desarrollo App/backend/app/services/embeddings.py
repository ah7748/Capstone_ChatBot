"""Embeddings: Azure OpenAI (real) o hash determinista (dev/test sin credenciales)."""
import hashlib
import math

import httpx

from app.core.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.EMBEDDINGS_BACKEND == "azure_openai":
        return await _azure_openai(texts)
    return [_hash_embedding(t) for t in texts]


async def _azure_openai(texts: list[str]) -> list[list[float]]:
    url = (f"{settings.AZURE_OPENAI_ENDPOINT}/openai/deployments/"
           f"{settings.AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT}/embeddings?api-version=2024-02-01")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json={"input": texts},
                              headers={"api-key": settings.AZURE_OPENAI_API_KEY})
        r.raise_for_status()
        data = r.json()["data"]
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]


def _hash_embedding(text: str, dim: int | None = None) -> list[float]:
    """Embedding determinista basado en n-gramas hasheados. Solo para dev/test:
    conserva similitud léxica aproximada, suficiente para probar el pipeline RAG."""
    dim = dim or settings.EMBEDDING_DIM
    vec = [0.0] * dim
    tokens = text.lower().split()
    grams = tokens + [" ".join(tokens[i:i + 2]) for i in range(len(tokens) - 1)]
    for g in grams:
        h = int.from_bytes(hashlib.sha1(g.encode()).digest()[:8], "big")
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return s / (na * nb)
