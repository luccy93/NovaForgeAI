import os, uuid
class SubscriptionManager:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def create(self, org_id, plan):
        return {"id": uuid.uuid4().hex, "org_id": org_id, "plan": plan}
