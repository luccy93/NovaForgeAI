import os, uuid
class EmbeddingService:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def search(self, collection, query, top_k=5):
        return []
