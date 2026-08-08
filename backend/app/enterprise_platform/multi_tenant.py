import os, uuid
class MultiTenant:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def provision(self, org_id, domain):
        return {"id": uuid.uuid4().hex, "org_id": org_id, "domain": domain}
