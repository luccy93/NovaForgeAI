"""NovaForge CLI — nova command-line tool with interactive and JSON modes."""

import argparse
import json
import os
import sys
from typing import Any, Optional

from backend.sdk.client import NovaForgeClient
from backend.sdk.exceptions import NovaForgeError


CONFIG_DIR = os.path.expanduser("~/.config/novaforge")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _save_config(config: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _get_client(json_output: bool = False) -> NovaForgeClient:
    config = _load_config()
    return NovaForgeClient(
        base_url=config.get("base_url", "http://localhost:8000"),
        access_token=config.get("access_token"),
        api_key=config.get("api_key"),
    )


def _print(data: Any, json_output: bool = False):
    if json_output:
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                print(f"  {item.get('name', item.get('id', '')):30} {item.get('description', '')[:60]}")
            else:
                print(f"  {item}")
    elif isinstance(data, dict):
        for k, v in data.items():
            if not isinstance(v, (dict, list)):
                print(f"  {k}: {v}")
    else:
        print(data)


def cmd_login(args):
    config = _load_config()
    client = NovaForgeClient(base_url=args.url or config.get("base_url", "http://localhost:8000"))
    try:
        resp = client.login(args.email, args.password)
        config["access_token"] = resp["access_token"]
        config["base_url"] = args.url or config.get("base_url", "http://localhost:8000")
        _save_config(config)
        print("✓ Logged in successfully")
    except NovaForgeError as e:
        print(f"✗ Login failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_logout(args):
    config = _load_config()
    config.pop("access_token", None)
    config.pop("api_key", None)
    _save_config(config)
    print("✓ Logged out")


def cmd_status(args):
    client = _get_client(args.json)
    try:
        me = client.me()
        orgs = client.list_organizations()
        agents = client.list_agents()
        result = {
            "user": {"id": me.id, "email": me.email, "username": me.username},
            "organizations": len(orgs),
            "agents": len(agents),
            "connected": True,
        }
        _print(result, args.json)
    except NovaForgeError as e:
        _print({"connected": False, "error": str(e)}, args.json)


def cmd_agents(args):
    client = _get_client(args.json)
    agents = client.list_agents()
    _print([{"name": a.name, "role": a.role, "description": a.description} for a in agents], args.json)


def cmd_run(args):
    client = _get_client(args.json)
    result = client.run_agent(args.name, args.task)
    _print(result, args.json)


def cmd_pipeline(args):
    client = _get_client(args.json)
    agents = [a.strip() for a in args.agents.split(",")]
    result = client.run_pipeline(agents, args.task)
    _print(result, args.json)


def cmd_notifications(args):
    client = _get_client(args.json)
    notifications = client.list_notifications()
    _print([{"title": n.title, "body": n.body, "is_read": n.is_read} for n in notifications], args.json)


def cmd_orgs(args):
    client = _get_client(args.json)
    orgs = client.list_organizations()
    _print([{"name": o.name, "slug": o.slug, "plan": o.plan} for o in orgs], args.json)


def cmd_config_set(args):
    config = _load_config()
    config[args.key] = args.value
    _save_config(config)
    print(f"✓ Set {args.key} = {args.value}")


def cmd_config_get(args):
    config = _load_config()
    key = args.key
    if key:
        val = config.get(key)
        if val is None:
            print(f"Config key '{key}' not set")
        else:
            print(f"{key}: {val}")
    else:
        for k, v in config.items():
            print(f"{k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="NovaForge AI CLI")
    parser.add_argument("--json", action="store_true", help="JSON output mode")

    sub = parser.add_subparsers(dest="command")

    p_login = sub.add_parser("login", help="Authenticate with NovaForge")
    p_login.add_argument("email")
    p_login.add_argument("password")
    p_login.add_argument("--url", help="NovaForge API URL")

    sub.add_parser("logout", help="Clear authentication")

    p_status = sub.add_parser("status", help="Show connection and user status")

    p_agents = sub.add_parser("agents", help="List available agents")
    p_run = sub.add_parser("run", help="Run an agent")
    p_run.add_argument("name", help="Agent name")
    p_run.add_argument("task", help="Task description")

    p_pipeline = sub.add_parser("pipeline", help="Run a multi-agent pipeline")
    p_pipeline.add_argument("agents", help="Comma-separated agent names")
    p_pipeline.add_argument("task", help="Task description")

    p_notifications = sub.add_parser("notifications", help="List notifications")
    p_orgs = sub.add_parser("orgs", help="List organizations")

    p_config = sub.add_parser("config", help="Configuration")
    p_config_sub = p_config.add_subparsers(dest="config_action")
    p_config_set = p_config_sub.add_parser("set", help="Set config value")
    p_config_set.add_argument("key")
    p_config_set.add_argument("value")
    p_config_get = p_config_sub.add_parser("get", help="Get config value")
    p_config_get.add_argument("key", nargs="?")

    args = parser.parse_args()

    cmds = {
        "login": cmd_login,
        "logout": cmd_logout,
        "status": cmd_status,
        "agents": cmd_agents,
        "run": cmd_run,
        "pipeline": cmd_pipeline,
        "notifications": cmd_notifications,
        "orgs": cmd_orgs,
    }

    if args.command in cmds:
        cmds[args.command](args)
    elif args.command == "config":
        if args.config_action == "set":
            cmd_config_set(args)
        elif args.config_action == "get":
            cmd_config_get(args)
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
