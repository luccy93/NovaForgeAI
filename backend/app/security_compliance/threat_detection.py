import os, uuid
class ThreatDetection:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
