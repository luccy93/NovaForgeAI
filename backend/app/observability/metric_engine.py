import os, uuid
class MetricEngine:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def ingest(self, name, value, tags=None):
        return {"id": uuid.uuid4().hex, "name": name, "value": value}
