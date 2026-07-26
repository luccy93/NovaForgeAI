import os, uuid
class SLOEngine:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
