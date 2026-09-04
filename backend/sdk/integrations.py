"""Integrations SDK mixin — Volume 70 Commit 1."""

from typing import Any, Dict, Optional


class IntegrationMixin:
    def integrations_list(self, status: str = "", limit: int = 100) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/integrations"), params=params)

    def integrations_create(self, name: str, type: str, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations"), data={"name": name, "type": type, **fields})

    def integrations_get(self, integration_id: str) -> dict:
        return self.get(self._build_url(f"/integrations/{integration_id}"))

    def integrations_update(self, integration_id: str, **fields: Any) -> dict:
        return self.patch(self._build_url(f"/integrations/{integration_id}"), data=fields)

    def integrations_set_status(self, integration_id: str, status: str) -> dict:
        return self.post(self._build_url(f"/integrations/{integration_id}/status"), data={"status": status})

    def integrations_create_connection(self, integration_id: str, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations/connections"),
                         data={"integration_id": integration_id, **fields})

    def integrations_connection_status(self, connection_id: str) -> dict:
        return self.get(self._build_url(f"/integrations/connections/{connection_id}"))

    def integrations_execute(self, connection_id: str, operation: str = "", **fields: Any) -> dict:
        return self.post(self._build_url(f"/integrations/connections/{connection_id}/execute"),
                         data={"operation": operation, **fields})

    def integrations_create_webhook(self, name: str, url: str, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations/webhooks"),
                         data={"name": name, "url": url, **fields})

    def integrations_webhook_status(self, webhook_id: str) -> dict:
        return self.get(self._build_url(f"/integrations/webhooks/{webhook_id}"))

    def integrations_delivery_history(self, webhook_id: str, limit: int = 100) -> dict:
        return self.get(self._build_url(f"/integrations/webhooks/{webhook_id}/deliveries"),
                        params={"limit": limit})

    def integrations_health(self, connection_id: str) -> dict:
        return self.post(self._build_url(f"/integrations/connections/{connection_id}/health"), data={})

    # ── Volume 70 Commit 2 — OAuth, connectors, governance ───────────────────

    def integrations_oauth_start(self, integration_id: str, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations/oauth/start"),
                         data={"integration_id": integration_id, **fields})

    def integrations_oauth_callback(self, state: str, code: str, token_endpoint: str) -> dict:
        return self.post(self._build_url("/integrations/oauth/callback"),
                         data={"state": state, "code": code, "token_endpoint": token_endpoint})

    def integrations_oauth_refresh(self, oauth_id: str, token_endpoint: str) -> dict:
        return self.post(self._build_url(f"/integrations/oauth/{oauth_id}/refresh"),
                         data={"token_endpoint": token_endpoint})

    def integrations_oauth_revoke(self, oauth_id: str) -> dict:
        return self.post(self._build_url(f"/integrations/oauth/{oauth_id}/revoke"), data={})

    def integrations_connectors_available(self) -> dict:
        return self.get(self._build_url("/integrations/connectors/available"))

    def integrations_connector_sync(self, connection_id: str, **fields: Any) -> dict:
        return self.post(self._build_url(f"/integrations/connections/{connection_id}/sync"), data=fields)

    def integrations_create_policy(self, name: str, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations/policies"), data={"name": name, **fields})

    def integrations_evaluate_transfer(self, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations/policies/evaluate-transfer"), data=fields)

    def integrations_ai_request(self, **fields: Any) -> dict:
        return self.post(self._build_url("/integrations/ai/request-action"), data=fields)


class AsyncIntegrationMixin:
    async def integrations_list(self, status: str = "", limit: int = 100) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/integrations"), params=params)

    async def integrations_create(self, name: str, type: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations"), data={"name": name, "type": type, **fields})

    async def integrations_get(self, integration_id: str) -> dict:
        return await self.get(self._build_url(f"/integrations/{integration_id}"))

    async def integrations_update(self, integration_id: str, **fields: Any) -> dict:
        return await self.patch(self._build_url(f"/integrations/{integration_id}"), data=fields)

    async def integrations_set_status(self, integration_id: str, status: str) -> dict:
        return await self.post(self._build_url(f"/integrations/{integration_id}/status"), data={"status": status})

    async def integrations_create_connection(self, integration_id: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations/connections"),
                               data={"integration_id": integration_id, **fields})

    async def integrations_connection_status(self, connection_id: str) -> dict:
        return await self.get(self._build_url(f"/integrations/connections/{connection_id}"))

    async def integrations_execute(self, connection_id: str, operation: str = "", **fields: Any) -> dict:
        return await self.post(self._build_url(f"/integrations/connections/{connection_id}/execute"),
                               data={"operation": operation, **fields})

    async def integrations_create_webhook(self, name: str, url: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations/webhooks"),
                               data={"name": name, "url": url, **fields})

    async def integrations_webhook_status(self, webhook_id: str) -> dict:
        return await self.get(self._build_url(f"/integrations/webhooks/{webhook_id}"))

    async def integrations_delivery_history(self, webhook_id: str, limit: int = 100) -> dict:
        return await self.get(self._build_url(f"/integrations/webhooks/{webhook_id}/deliveries"),
                              params={"limit": limit})

    async def integrations_health(self, connection_id: str) -> dict:
        return await self.post(self._build_url(f"/integrations/connections/{connection_id}/health"), data={})

    # ── Volume 70 Commit 2 — OAuth, connectors, governance ───────────────────

    async def integrations_oauth_start(self, integration_id: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations/oauth/start"),
                               data={"integration_id": integration_id, **fields})

    async def integrations_oauth_callback(self, state: str, code: str, token_endpoint: str) -> dict:
        return await self.post(self._build_url("/integrations/oauth/callback"),
                               data={"state": state, "code": code, "token_endpoint": token_endpoint})

    async def integrations_oauth_revoke(self, oauth_id: str) -> dict:
        return await self.post(self._build_url(f"/integrations/oauth/{oauth_id}/revoke"), data={})

    async def integrations_connector_sync(self, connection_id: str, **fields: Any) -> dict:
        return await self.post(self._build_url(f"/integrations/connections/{connection_id}/sync"), data=fields)

    async def integrations_oauth_refresh(self, oauth_id: str, token_endpoint: str) -> dict:
        return await self.post(self._build_url(f"/integrations/oauth/{oauth_id}/refresh"),
                               data={"token_endpoint": token_endpoint})

    async def integrations_connectors_available(self) -> dict:
        return await self.get(self._build_url("/integrations/connectors/available"))

    async def integrations_create_policy(self, name: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations/policies"), data={"name": name, **fields})

    async def integrations_evaluate_transfer(self, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations/policies/evaluate-transfer"), data=fields)

    async def integrations_ai_request(self, **fields: Any) -> dict:
        return await self.post(self._build_url("/integrations/ai/request-action"), data=fields)
