import os, uuid
class DashboardEngine:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def get(self, dashboard_id):
        return {"id": dashboard_id, "widgets": []}
