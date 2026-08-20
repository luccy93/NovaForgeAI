"""Marketplace SDK mixin — search, publish, install, configure, review, report.

Mirrors :mod:`backend.sdk.rag` and expects the host class to provide
``self.get/post/put/patch/delete`` and ``self._build_url``.
"""

from typing import Any, Optional


class MarketplaceMixin:
    def marketplace_search(
        self,
        query: Optional[str] = None,
        package_type: Optional[str] = None,
        category: Optional[str] = None,
        publisher: Optional[str] = None,
        min_rating: Optional[float] = None,
        pricing_type: Optional[str] = None,
        license: Optional[str] = None,
        sort: str = "relevance",
        include_private: bool = False,
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        params: dict[str, Any] = {"sort": sort, "include_private": include_private, "limit": limit, "offset": offset}
        for k, v in (
            ("q", query), ("package_type", package_type), ("category", category),
            ("publisher", publisher), ("min_rating", min_rating),
            ("pricing_type", pricing_type), ("license", license),
        ):
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/marketplace/search"), params=params)

    def marketplace_get_package(self, slug: str) -> dict:
        return self.get(self._build_url(f"/marketplace/packages/{slug}"))

    def marketplace_list_packages(self, package_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> list:
        params = {"limit": limit, "offset": offset}
        if package_type:
            params["package_type"] = package_type
        return self.get(self._build_url("/marketplace/packages"), params=params)

    def marketplace_categories(self) -> dict:
        return self.get(self._build_url("/marketplace/categories"))

    def marketplace_create_publisher(self, data: dict) -> dict:
        return self.post(self._build_url("/marketplace/publishers"), data=data)

    def marketplace_verify_publisher(self, publisher_id: str, method: str, token: Optional[str] = None) -> dict:
        payload = {"method": method, "token": token}
        return self.post(self._build_url(f"/marketplace/publishers/{publisher_id}/verify"), data=payload)

    def marketplace_create_package(self, data: dict) -> dict:
        return self.post(self._build_url("/marketplace/packages"), data=data)

    def marketplace_publish_release(self, slug: str, data: dict) -> dict:
        return self.post(self._build_url(f"/marketplace/packages/{slug}/releases"), data=data)

    def marketplace_install(self, data: dict) -> dict:
        return self.post(self._build_url("/marketplace/install"), data=data)

    def marketplace_list_installations(self, environment: Optional[str] = None) -> list:
        params = {}
        if environment:
            params["environment"] = environment
        return self.get(self._build_url("/marketplace/installations"), params=params)

    def marketplace_configure_installation(self, installation_id: str, configuration: dict) -> dict:
        return self.put(self._build_url(f"/marketplace/installations/{installation_id}"), data={"configuration": configuration})

    def marketplace_update(self, installation_id: str, version: Optional[str] = None) -> dict:
        params = {}
        if version:
            params["version"] = version
        return self.post(self._build_url(f"/marketplace/installations/{installation_id}/update"), params=params)

    def marketplace_rollback(self, installation_id: str, version: str, emergency: bool = False) -> dict:
        return self.post(
            self._build_url(f"/marketplace/installations/{installation_id}/rollback"),
            params={"version": version, "emergency": emergency},
        )

    def marketplace_uninstall(self, installation_id: str) -> dict:
        return self.post(self._build_url(f"/marketplace/installations/{installation_id}/uninstall"), data={})

    def marketplace_create_review(self, data: dict) -> dict:
        return self.post(self._build_url("/marketplace/reviews"), data=data)

    def marketplace_create_report(self, data: dict) -> dict:
        return self.post(self._build_url("/marketplace/reports"), data=data)

    def marketplace_validate_config(self, schema_fields: list, values: dict) -> dict:
        return self.post(
            self._build_url("/marketplace/configuration/validate"),
            data={"schema_fields": schema_fields, "values": values},
        )

    def marketplace_package_health(self, slug: str) -> dict:
        return self.get(self._build_url(f"/marketplace/packages/{slug}/health"))


class AsyncMarketplaceMixin:
    async def marketplace_search(
        self,
        query: Optional[str] = None,
        package_type: Optional[str] = None,
        category: Optional[str] = None,
        publisher: Optional[str] = None,
        min_rating: Optional[float] = None,
        pricing_type: Optional[str] = None,
        license: Optional[str] = None,
        sort: str = "relevance",
        include_private: bool = False,
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        params: dict[str, Any] = {"sort": sort, "include_private": include_private, "limit": limit, "offset": offset}
        for k, v in (
            ("q", query), ("package_type", package_type), ("category", category),
            ("publisher", publisher), ("min_rating", min_rating),
            ("pricing_type", pricing_type), ("license", license),
        ):
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/marketplace/search"), params=params)

    async def marketplace_get_package(self, slug: str) -> dict:
        return await self.get(self._build_url(f"/marketplace/packages/{slug}"))

    async def marketplace_create_publisher(self, data: dict) -> dict:
        return await self.post(self._build_url("/marketplace/publishers"), data=data)

    async def marketplace_create_package(self, data: dict) -> dict:
        return await self.post(self._build_url("/marketplace/packages"), data=data)

    async def marketplace_publish_release(self, slug: str, data: dict) -> dict:
        return await self.post(self._build_url(f"/marketplace/packages/{slug}/releases"), data=data)

    async def marketplace_install(self, data: dict) -> dict:
        return await self.post(self._build_url("/marketplace/install"), data=data)

    async def marketplace_list_installations(self, environment: Optional[str] = None) -> list:
        params = {}
        if environment:
            params["environment"] = environment
        return await self.get(self._build_url("/marketplace/installations"), params=params)

    async def marketplace_update(self, installation_id: str, version: Optional[str] = None) -> dict:
        params = {}
        if version:
            params["version"] = version
        return await self.post(self._build_url(f"/marketplace/installations/{installation_id}/update"), params=params)

    async def marketplace_rollback(self, installation_id: str, version: str, emergency: bool = False) -> dict:
        return await self.post(
            self._build_url(f"/marketplace/installations/{installation_id}/rollback"),
            params={"version": version, "emergency": emergency},
        )

    async def marketplace_uninstall(self, installation_id: str) -> dict:
        return await self.post(self._build_url(f"/marketplace/installations/{installation_id}/uninstall"), data={})

    async def marketplace_create_review(self, data: dict) -> dict:
        return await self.post(self._build_url("/marketplace/reviews"), data=data)

    async def marketplace_create_report(self, data: dict) -> dict:
        return await self.post(self._build_url("/marketplace/reports"), data=data)

    async def marketplace_validate_config(self, schema_fields: list, values: dict) -> dict:
        return await self.post(
            self._build_url("/marketplace/configuration/validate"),
            data={"schema_fields": schema_fields, "values": values},
        )
