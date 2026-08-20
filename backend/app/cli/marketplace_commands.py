"""Marketplace CLI — ``nova marketplace <command>``.

Talks to the Marketplace REST API over HTTP (Bearer token). Mirrors
:mod:`app.cli.rag_commands`.
"""

import argparse
import asyncio
import json
import os
import sys

import httpx


def _red(s):
    return f"\033[91m{s}\033[0m" if sys.stdout.isatty() else s


def _green(s):
    return f"\033[92m{s}\033[0m" if sys.stdout.isatty() else s


def _print_json(data):
    print(json.dumps(data, indent=2, default=str))


class MarketplaceCLICommands:
    def __init__(self, base_url, api_key=None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def _url(self, path):
        return f"{self.base_url}{path}"

    async def _request(self, method, path, json=None, params=None, verbose=False):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, self._url(path), json=json, params=params, headers=self.headers)
            if verbose:
                print(f"{method} {path} -> {resp.status_code}", file=sys.stderr)
            if resp.status_code == 204:
                return {}
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            if resp.status_code >= 400:
                raise SystemExit(_red(f"error {resp.status_code}: {body}"))
            return body

    async def search(self, args, verbose=False):
        params = {"limit": args.limit, "offset": 0, "sort": args.sort}
        if args.query:
            params["q"] = args.query
        if args.type:
            params["package_type"] = args.type
        if args.category:
            params["category"] = args.category
        data = await self._request("GET", "/api/v1/marketplace/search", params=params, verbose=verbose)
        items = data.get("items", [])
        if args.json:
            _print_json(data)
        else:
            for it in items:
                print(f"{_green(it['slug'])}  {it['name']}  [{it['package_type']}]  v{it.get('latest_version')}  rating={it.get('average_rating')}  {it['pricing_type']}")
            print(f"\n{len(items)} of {data.get('total')} results")
        return data

    async def info(self, args, verbose=False):
        data = await self._request("GET", f"/api/v1/marketplace/packages/{args.slug}", verbose=verbose)
        if args.json:
            _print_json(data)
        else:
            print(f"{_green(data['name'])} ({data['slug']})")
            print(f"  type:     {data['package_type']}")
            print(f"  version:  {data.get('latest_version')}")
            print(f"  status:   {data['status']}  governance={data['governance_status']}  security={data['security_status']}")
            print(f"  license:  {data['license']}  pricing: {data['pricing_type']}")
            print(f"  rating:   {data['average_rating']} ({data['rating_count']} reviews)  installs={data['install_count']}")
            print(f"  desc:     {data['description'][:200]}")
        return data

    async def list_(self, args, verbose=False):
        params = {"limit": args.limit, "offset": 0}
        if args.environment:
            params["environment"] = args.environment
        data = await self._request("GET", "/api/v1/marketplace/installations", params=params, verbose=verbose)
        items = data if isinstance(data, list) else data.get("items", [])
        if args.json:
            _print_json(items)
        else:
            for it in items:
                print(f"{it['id']}  {it['package_slug'] or it['package_id']}  v{it['current_version']}  {it['environment']}  {it['status']}  approval={it['approval_status']}")
        return items

    async def install(self, args, verbose=False):
        payload = {"package_slug": args.slug, "environment": args.environment, "configuration": json.loads(args.config) if args.config else {}}
        if args.version:
            payload["version"] = args.version
        if args.workspace:
            payload["workspace_id"] = args.workspace
        data = await self._request("POST", "/api/v1/marketplace/install", json=payload, verbose=verbose)
        print(_green("installed" if data.get("status") == "active" else f"install recorded (status={data.get('status')})"))
        if args.json:
            _print_json(data)
        return data

    async def uninstall(self, args, verbose=False):
        data = await self._request("POST", f"/api/v1/marketplace/installations/{args.installation_id}/uninstall", json={}, verbose=verbose)
        print(_green("uninstalled"))
        if args.json:
            _print_json(data)
        return data

    async def update(self, args, verbose=False):
        params = {}
        if args.version:
            params["version"] = args.version
        data = await self._request("POST", f"/api/v1/marketplace/installations/{args.installation_id}/update", params=params, verbose=verbose)
        print(_green(f"updated to {data.get('current_version')}"))
        if args.json:
            _print_json(data)
        return data

    async def rollback(self, args, verbose=False):
        data = await self._request(
            "POST", f"/api/v1/marketplace/installations/{args.installation_id}/rollback",
            params={"version": args.version, "emergency": args.emergency}, verbose=verbose,
        )
        print(_green(f"rolled back to {data.get('current_version')}"))
        if args.json:
            _print_json(data)
        return data

    async def publish(self, args, verbose=False):
        manifest = json.loads(open(args.manifest).read())
        payload = {"version": args.version, "manifest": manifest, "changelog": args.changelog or "", "artifacts": json.loads(args.artifacts) if args.artifacts else []}
        data = await self._request("POST", f"/api/v1/marketplace/packages/{args.slug}/releases", json=payload, verbose=verbose)
        print(_green(f"published {args.version}"))
        if args.json:
            _print_json(data)
        return data

    async def validate(self, args, verbose=False):
        manifest = json.loads(open(args.manifest).read())
        from app.marketplace.manifest import validate_manifest

        m, errors = validate_manifest(manifest)
        if errors:
            print(_red("INVALID:"))
            for e in errors:
                print("  - " + e)
            raise SystemExit(1)
        print(_green("manifest valid"))
        return True


def _build_parser():
    p = argparse.ArgumentParser(prog="nova marketplace", description="NovaForge Marketplace CLI")
    p.add_argument("--base-url", default=os.environ.get("NOVAFORGE_API_URL", "http://localhost:8000"))
    p.add_argument("--token", default=os.environ.get("NOVAFORGE_TOKEN"))
    p.add_argument("--json", action="store_true", help="output raw JSON")
    p.add_argument("--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search"); sp.add_argument("query", nargs="?", default=None); sp.add_argument("--type"); sp.add_argument("--category"); sp.add_argument("--sort", default="relevance"); sp.add_argument("--limit", type=int, default=25)
    sp = sub.add_parser("info"); sp.add_argument("slug")
    sp = sub.add_parser("list"); sp.add_argument("--environment"); sp.add_argument("--limit", type=int, default=50)
    sp = sub.add_parser("install"); sp.add_argument("slug"); sp.add_argument("--version"); sp.add_argument("--environment", default="production"); sp.add_argument("--workspace"); sp.add_argument("--config", default=None)
    sp = sub.add_parser("uninstall"); sp.add_argument("installation_id")
    sp = sub.add_parser("update"); sp.add_argument("installation_id"); sp.add_argument("--version")
    sp = sub.add_parser("rollback"); sp.add_argument("installation_id"); sp.add_argument("version"); sp.add_argument("--emergency", action="store_true")
    sp = sub.add_parser("publish"); sp.add_argument("slug"); sp.add_argument("manifest"); sp.add_argument("version"); sp.add_argument("--changelog", default=""); sp.add_argument("--artifacts", default=None)
    sp = sub.add_parser("validate"); sp.add_argument("manifest")
    return p


async def _dispatch(args):
    cli = MarketplaceCLICommands(base_url=args.base_url, api_key=args.token)
    handlers = {
        "search": cli.search, "info": cli.info, "list": cli.list_,
        "install": cli.install, "uninstall": cli.uninstall, "update": cli.update,
        "rollback": cli.rollback, "publish": cli.publish, "validate": cli.validate,
    }
    return await handlers[args.command](args, verbose=args.verbose)


def marketplace_cli_main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_dispatch(args))
    except KeyboardInterrupt:
        raise SystemExit(1)


if __name__ == "__main__":
    marketplace_cli_main()
