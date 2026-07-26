import os, uuid
class UserManagement:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def authenticate(self, org_id, email):
        return {"id": uuid.uuid4().hex, "email": email}
