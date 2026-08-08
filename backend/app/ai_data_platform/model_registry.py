import os, uuid
class ModelRegistry:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def register(self, name, version, uri, framework=""):
        return {"id": uuid.uuid4().hex, "name": name, "version": version}
