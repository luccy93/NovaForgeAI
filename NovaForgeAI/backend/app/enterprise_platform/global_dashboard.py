import os, uuid
class GlobalDashboard:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def get(self, org_id):
        return {"org_id": org_id, "sections": []}
