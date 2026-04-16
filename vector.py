import config
import chromadb
import uuid
import time

class ConversationVector:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
        self.summary_collection = self.client.get_or_create_collection(
            name=config.COLLECTION_SUMMARY_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        self.raw_collection = self.client.get_or_create_collection(
            name=config.COLLECTION_RAW_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    def add(self, summary:str, raw: str, embedding: list) -> None:
        ids = str(uuid.uuid4())
        time_in = time.time_ns()
        self.summary_collection.add(
            ids=[ids],
            documents=[summary],
            embeddings = embedding,
            metadatas=[{"time": time_in}]
        )
        self.raw_collection.add(
            ids=[ids],
            documents=[raw],
            metadatas=[{"time": time_in}]
        )

    def compare(self, embedding: list) -> float:
        result = self.summary_collection.query(
            query_embeddings=embedding,
            n_results=1
        )
        distance = result['distances'][0][0]
        return (1 - distance) / 2 + 0.5

    def search(self, embedding: list, top_k: int) -> list:
        result = self.summary_collection.query(
             query_embeddings=embedding,
             n_results=top_k
        )
        result = self.raw_collection.get(ids=result['ids'][0])
        return result["documents"]