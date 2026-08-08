import os, uuid
class IncidentResponse:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
