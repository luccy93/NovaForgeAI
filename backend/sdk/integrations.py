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
