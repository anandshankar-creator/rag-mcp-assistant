"""
==============================================================================
Module: rag.vectorstore
Role in Architecture: Persistent Vector Store (ChromaDB Manager)
==============================================================================
Manages local persistent storage and nearest-neighbor vector search using ChromaDB.

Design Choices for Review:
1. Local & Persistent: Data is saved to SQLite/DuckDB-backed parquet files inside
   `db/chroma/`, meaning the database persists across server restarts without re-embedding.
2. Cosine Distance Metric: We configure `{"hnsw:space": "cosine"}`. ChromaDB returns
   cosine distance $d \in [0, 2]$. We convert this to cosine similarity $s = 1.0 - d$.
3. Document Lifecycle Management: Supports deleting and re-ingesting individual files
   when a student updates their notes or syllabus, avoiding full database rebuilds.
"""

from __future__ import annotations
import sys
# Safe sqlite3 monkey-patch for Streamlit Cloud Linux environments
try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

from pathlib import Path
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from rag.chunking import Chunk
from rag.embeddings import embed_documents, embed_query


class VectorStore:
    """Encapsulates ChromaDB collection lifecycle and similarity queries."""

    COLLECTION_NAME = "student_knowledge_base"

    def __init__(self, persist_directory: Optional[Path | str] = None):
        self.persist_dir = Path(persist_directory or settings.CHROMA_PERSIST_DIR).resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize persistent client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Get or create collection with cosine similarity space
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: List[Chunk], batch_size: int = 64) -> int:
        """
        Embeds and upserts chunks into the ChromaDB collection.
        Uses batched execution to handle large document sets smoothly.
        """
        if not chunks:
            return 0

        total_added = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            ids = [c.chunk_id for c in batch]
            texts = [c.text for c in batch]
            metadatas = [c.metadata for c in batch]

            # Generate vectors
            embeddings = embed_documents(texts)

            # Upsert into collection (upsert avoids duplicate key conflicts)
            self.collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            total_added += len(batch)

        print(f"[VECTORSTORE] Upserted {total_added} chunks into '{self.COLLECTION_NAME}'.")
        return total_added

    def delete_document(self, filename: str) -> int:
        """
        Removes all indexed chunks associated with a specific document filename.
        """
        try:
            # Query for IDs belonging to this source_file
            results = self.collection.get(
                where={"source_file": filename},
                include=["metadatas"],
            )
            ids_to_delete = results.get("ids", [])
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                print(f"[VECTORSTORE] Deleted {len(ids_to_delete)} chunks for '{filename}'.")
                return len(ids_to_delete)
            return 0
        except Exception as e:
            print(f"[ERROR] Failed to delete document '{filename}': {e}")
            return 0

    def query_similarity(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top-k closest chunks to the query string.
        Calculates cosine similarity score: similarity = 1.0 - distance.

        Returns list of structured dicts:
            {
                "chunk_id": str,
                "text": str,
                "metadata": dict,
                "similarity": float,
                "source_file": str,
                "page": int
            }
        """
        k = top_k or settings.RAG_TOP_K
        query_vector = embed_query(query)
        if not query_vector:
            return []

        try:
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )

            matched_chunks: List[Dict[str, Any]] = []

            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            ids = results.get("ids", [[]])[0]

            for doc, meta, dist, c_id in zip(docs, metas, distances, ids):
                # In cosine space, cosine distance d = 1 - cosine_sim, so sim = 1.0 - dist
                sim_score = max(0.0, min(1.0, 1.0 - float(dist)))
                matched_chunks.append({
                    "chunk_id": c_id,
                    "text": doc,
                    "metadata": meta,
                    "similarity": round(sim_score, 4),
                    "source_file": meta.get("source_file", "unknown"),
                    "page": meta.get("page", 1),
                })

            return matched_chunks

        except Exception as e:
            print(f"[ERROR] Similarity query failed: {e}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics for the admin dashboard and debug trace."""
        try:
            count = self.collection.count()
            all_records = self.collection.get(include=["metadatas"])
            source_files = set()
            for m in all_records.get("metadatas", []):
                if m and "source_file" in m:
                    source_files.add(m["source_file"])

            return {
                "collection_name": self.COLLECTION_NAME,
                "total_chunks": count,
                "source_files": sorted(list(source_files)),
                "storage_directory": str(self.persist_dir),
            }
        except Exception as e:
            return {"error": str(e), "total_chunks": 0, "source_files": []}

    def clear_collection(self) -> None:
        """Deletes all items in the collection (useful for full re-indexing)."""
        try:
            self.client.delete_collection(name=self.COLLECTION_NAME)
            self.collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            print(f"[VECTORSTORE] Reset collection '{self.COLLECTION_NAME}'.")
        except Exception as e:
            print(f"[ERROR] Failed to clear collection: {e}")


# Singleton instance
_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Factory providing access to the persistent VectorStore singleton."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance


if __name__ == "__main__":
    print("Testing VectorStore initialization...")
    store = get_vector_store()
    stats = store.get_collection_stats()
    print(f"Stats: {stats}")
