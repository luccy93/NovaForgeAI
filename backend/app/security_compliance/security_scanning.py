import os, uuid
class SecurityScanning:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def scan(self, repo_id, scan_type="full"):
        return type("obj", (), {"id": uuid.uuid4().hex})()
    def get_findings(self, scan_id):
        return []
