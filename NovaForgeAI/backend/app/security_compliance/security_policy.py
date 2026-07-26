import os, uuid
class SecurityPolicy:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
