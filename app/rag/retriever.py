from typing import Optional
from sqlalchemy import text
import logging

from app.core.config import settings
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_embedder = None
_chroma_client = None
_chroma_collection = None


def get_embedder():
    global _embedder
    if _embedder is None:
        try:
            from fastembed import TextEmbedding
            _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            logger.info("FastEmbed embedder loaded OK")
        except Exception as e:
            logger.error(f"FastEmbed load failed: {e}")
            _embedder = None
    return _embedder


def embed_text(text_input: str) -> Optional[list]:
    embedder = get_embedder()
    if embedder is None:
        return None
    try:
        result = list(embedder.embed([text_input]))
        return result[0].tolist()
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return None


def get_chroma():
    global _chroma_client, _chroma_collection
    if _chroma_client is None:
        try:
            import chromadb
            _chroma_client = chromadb.HttpClient(
                host=settings.CHROMADB_HOST,
                port=settings.CHROMADB_PORT,
            )
            _chroma_collection = _chroma_client.get_or_create_collection(
                name="codezen_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB connected OK")
        except Exception as e:
            logger.warning(f"ChromaDB not available: {e}")
            _chroma_client = None
            _chroma_collection = None
    return _chroma_collection


async def check_qa_cache(query: str) -> Optional[str]:
    embedding = embed_text(query)
    if embedding is None:
        return None
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("""
                    SELECT answer, 1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                    FROM qa_cache
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:emb AS vector)
                    LIMIT 1
                """),
                {"emb": str(embedding)},
            )
            row = result.fetchone()
            if row and float(row.similarity) >= settings.SIMILARITY_THRESHOLD:
                await db.execute(
                    text("UPDATE qa_cache SET hit_count = hit_count + 1, updated_at = NOW() WHERE answer = :ans"),
                    {"ans": row.answer},
                )
                await db.commit()
                logger.info(f"QA cache hit — similarity {float(row.similarity):.3f}")
                return row.answer
    except Exception as e:
        logger.error(f"Cache check error: {e}")
    return None


async def store_qa_cache(question: str, answer: str) -> None:
    embedding = embed_text(question)
    if embedding is None:
        return
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO qa_cache (id, question, answer, embedding, hit_count, created_at, updated_at)
                    VALUES (gen_random_uuid(), :q, :a, CAST(:emb AS vector), 0, :now, :now)
                    ON CONFLICT DO NOTHING
                """),
                {"q": question, "a": answer, "emb": str(embedding), "now": now},
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Cache store error: {e}")


async def retrieve_context(query: str) -> list[dict]:
    chunks = []

    # Try ChromaDB first
    try:
        collection = get_chroma()
        if collection is not None:
            embedding = embed_text(query)
            if embedding:
                results = collection.query(
                    query_embeddings=[embedding],
                    n_results=settings.MAX_RETRIEVED_CHUNKS,
                    include=["documents", "metadatas", "distances"],
                )
                if results and results.get("documents") and results["documents"][0]:
                    for doc, meta, dist in zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    ):
                        if dist < 0.6:
                            chunks.append({
                                "content": doc,
                                "source": meta.get("source", "unknown"),
                                "score": round(1 - dist, 4),
                            })
    except Exception as e:
        logger.error(f"ChromaDB retrieval error: {e}")

    # Fallback: pgvector search
    if not chunks:
        try:
            embedding = embed_text(query)
            if embedding:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        text("""
                            SELECT content, source,
                                   1 - (embedding <=> CAST(:emb AS vector)) AS score
                            FROM knowledge_chunks
                            WHERE embedding IS NOT NULL
                              AND 1 - (embedding <=> CAST(:emb AS vector)) > 0.35
                            ORDER BY embedding <=> CAST(:emb AS vector)
                            LIMIT :limit
                        """),
                        {"emb": str(embedding), "limit": settings.MAX_RETRIEVED_CHUNKS},
                    )
                    rows = result.fetchall()
                    chunks = [
                        {"content": r.content, "source": r.source, "score": round(float(r.score), 4)}
                        for r in rows
                    ]
        except Exception as e:
            logger.error(f"pgvector retrieval error: {e}")

    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks[:settings.MAX_RETRIEVED_CHUNKS]