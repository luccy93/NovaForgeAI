import os, uuid
class AlertManager:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
    def list_rules(self):
        return []
    def fire(self, rule_id):
        return {"fired": rule_id}
