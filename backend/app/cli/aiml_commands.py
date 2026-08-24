"""NovaForge AIML CLI — Volume 58.

Dispatch for ``nova ai`` subcommands: models, providers, prompts, evaluate,
approve, deploy, rollback, policy, risk, status.  Calls backend at
``{base}/api/v1/ai/...`` via httpx.  Supports --json and --ci flags.

Usage:
    python -m app.cli.aiml_commands models --provider openai
    nova ai models --json
    nova ai providers --ci
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _red(t: str) -> str:
    return f"{_RED}{t}{_RESET}"


def _green(t: str) -> str:
    return f"{_GREEN}{t}{_RESET}"


def _yellow(t: str) -> str:
    return f"{_YELLOW}{t}{_RESET}"


def _cyan(t: str) -> str:
    return f"{_CYAN}{t}{_RESET}"


def _bold(t: str) -> str:
    return f"{_BOLD}{t}{_RESET}"


def _dim(t: str) -> str:
    return f"{_DIM}{t}{_RESET}"


def _header(cmd: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{_bold(_cyan(f'[{cmd}]'))} {_dim(now)}"


def _print_header(cmd: str) -> None:
    print(_header(cmd))


def _print_error(msg: str) -> None:
    print(_red(f"Error: {msg}"), file=sys.stderr)


def _print_success(msg: str) -> None:
    print(_green(msg))


def _print_info(msg: str) -> None:
    print(_cyan(msg))


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# AIML CLI Commands class
# ---------------------------------------------------------------------------


class AIMLCLICommands:
    """CLI commands for NovaForge /api/v1/ai backend."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, ci: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ci = ci
        self._client_kwargs: dict[str, Any] = {"timeout": httpx.Timeout(30.0, connect=10.0)}
        if self.api_key:
            self._client_kwargs["headers"] = {"Authorization": f"Bearer {self.api_key}"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            h.update(extra)
        return h

    def _log_verbose(self, msg: str, verbose: bool) -> None:
        if verbose:
            print(_dim(f"[verbose] {msg}"), file=sys.stderr)

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        self._log_verbose(f"{method} {path} json={json_body} params={params}", verbose)
        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                resp = await client.request(
                    method,
                    self._url(path),
                    json=json_body,
                    params=params,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                if resp.status_code == 204:
                    return {"status": "ok"}
                return resp.json()
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    # -- models ---------------------------------------------------------------

    async def models(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header("models")
        params: dict[str, Any] = {}
        if provider:
            params["provider"] = provider
        if status:
            params["status"] = status
        data = await self._request("GET", "/api/v1/ai/models", params=params, verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        items = data if isinstance(data, list) else data.get("models", data.get("results", data if isinstance(data, dict) else []))
        if isinstance(items, list):
            print(f"\n{_bold(f'Models ({len(items)})')}\n")
            for i, m in enumerate(items, 1):
                if isinstance(m, dict):
                    name = m.get("name", m.get("model_id", "unknown"))
                    ver = m.get("version", "")
                    prov = m.get("provider", "")
                    st = m.get("status", "")
                    color = _green if st in ("APPROVED", "ACTIVE") else _yellow
                    print(f"  {_bold(f'{i}.')} {_cyan(str(name))} {_dim(str(ver))} {_dim(str(prov))} {color(str(st))}")
                else:
                    print(f"  {i}. {m}")
            print()
        else:
            _print_json(data)
        _print_success("Models retrieved")
        return data

    # -- providers ------------------------------------------------------------

    async def providers(
        self,
        provider: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header("providers")
        if provider:
            data = await self._request("GET", f"/api/v1/ai/providers/{provider}", verbose=verbose)
        else:
            data = await self._request("GET", "/api/v1/ai/providers", verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        if isinstance(data, list):
            print(f"\n{_bold(f'Providers ({len(data)})')}\n")
            for i, p in enumerate(data, 1):
                if isinstance(p, dict):
                    name = p.get("provider", p.get("display_name", "unknown"))
                    avail = p.get("availability", "")
                    color = _green if avail == "AVAILABLE" else _yellow
                    print(f"  {_bold(f'{i}.')} {_cyan(str(name))} {color(str(avail))}")
                else:
                    print(f"  {i}. {p}")
            print()
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (list, dict)):
                    _print_info(f"  {k}: ({type(v).__name__}, {len(v)} items)")
                else:
                    _print_info(f"  {k}: {v}")
        _print_success("Providers retrieved")
        return data

    # -- prompts --------------------------------------------------------------

    async def prompts(
        self,
        prompt_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header("prompts")
        if prompt_id:
            data = await self._request("GET", f"/api/v1/ai/prompts/{prompt_id}", verbose=verbose)
        else:
            data = await self._request("GET", "/api/v1/ai/prompts", verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        items = data if isinstance(data, list) else data.get("prompts", data.get("results", data if isinstance(data, list) else []))
        if isinstance(items, list):
            print(f"\n{_bold(f'Prompts ({len(items)})')}\n")
            for i, p in enumerate(items, 1):
                if isinstance(p, dict):
                    name = p.get("name", p.get("prompt_id", "unknown"))
                    cls = p.get("classification", "")
                    print(f"  {_bold(f'{i}.')} {_cyan(str(name))} {_dim(str(cls))}")
                else:
                    print(f"  {i}. {p}")
            print()
        elif isinstance(data, dict) and not as_json:
            for k, v in data.items():
                if isinstance(v, (list, dict)):
                    _print_info(f"  {k}: ({type(v).__name__}, {len(v)} items)")
                else:
                    _print_info(f"  {k}: {v}")
        _print_success("Prompts retrieved")
        return data

    # -- evaluate -------------------------------------------------------------

    async def evaluate(
        self,
        suite_id: Optional[str] = None,
        candidate_run_id: Optional[str] = None,
        baseline_run_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header("evaluate")
        if candidate_run_id and baseline_run_id:
            data = await self._request(
                "GET", "/api/v1/ai/evaluations/compare",
                params={"candidate_run_id": candidate_run_id, "baseline_run_id": baseline_run_id},
                verbose=verbose,
            )
        elif suite_id:
            # list runs for suite or get suite
            data = await self._request("GET", f"/api/v1/ai/evaluations/runs/{suite_id}", verbose=verbose)
            if data is None:
                # fallback: try suite listing
                data = await self._request("GET", "/api/v1/ai/evaluations/suites", verbose=verbose)
        else:
            # list recent evaluations — via compare endpoint without params not valid, so hit risks as placeholder health
            data = await self._request("GET", "/api/v1/ai/evaluations/compare",
                                        params={"candidate_run_id": candidate_run_id or "00000000-0000-0000-0000-000000000000",
                                                "baseline_run_id": baseline_run_id or "00000000-0000-0000-0000-000000000000"},
                                        verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        if isinstance(data, dict):
            verdict = data.get("verdict", data.get("decision", ""))
            color = _green if verdict in ("PASS", "ALLOW") else _red if verdict in ("BLOCK", "FAIL", "DENY") else _yellow
            if verdict:
                print(f"\n  {_bold('Verdict:')} {color(str(verdict))}")
            for k in ("failures", "has_regression", "is_block", "deltas", "regression_signals"):
                if k in data:
                    _print_info(f"  {k}: {data[k]}")
            print()
        else:
            _print_json(data)
        _print_success("Evaluation retrieved")
        return data

    # -- approve --------------------------------------------------------------

    async def approve(
        self,
        approval_id: str,
        approver: str,
        decision: str = "approved",
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header(f"approve/{approval_id}")
        payload = {"approver": approver, "decision": decision}
        data = await self._request("POST", f"/api/v1/ai/approvals/{approval_id}/decide", json_body=payload, verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        status = data.get("status", decision)
        color = _green if status in ("approved", "APPROVED") else _red if status in ("rejected", "REJECTED") else _yellow
        _print_success(f"Approval {approval_id} decided: {color(str(status))}")
        for k in ("request_type", "model_id", "provider", "version"):
            if k in data and data[k]:
                print(f"  {_bold(f'{k}:')} {data[k]}")
        print()
        return data

    # -- deploy ---------------------------------------------------------------

    async def deploy(
        self,
        model_id: str,
        environment: str = "production",
        version: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header(f"deploy/{model_id}")
        payload: dict[str, Any] = {"model_id": model_id, "environment": environment}
        if version:
            payload["version"] = version
        data = await self._request("POST", "/api/v1/ai/deployments", json_body=payload, verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        did = data.get("id", data.get("deployment_id", model_id))
        _print_success(f"Deployed {model_id} -> {environment} (deployment={did})")
        for k in ("status", "environment", "provider", "version"):
            if k in data and data[k]:
                print(f"  {_bold(f'{k}:')} {data[k]}")
        print()
        return data

    # -- rollback -------------------------------------------------------------

    async def rollback(
        self,
        deployment_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header(f"rollback/{deployment_id}")
        data = await self._request("POST", f"/api/v1/ai/deployments/{deployment_id}/rollback", verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        _print_success(f"Rollback {deployment_id} completed")
        for k in ("status", "rolled_back_at", "rolled_back_by"):
            if k in data and data[k]:
                print(f"  {_bold(f'{k}:')} {data[k]}")
        print()
        return data

    # -- policy ---------------------------------------------------------------

    async def policy(
        self,
        resource: Optional[str] = None,
        context: Optional[dict] = None,
        simulate: bool = False,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header(f"policy/{'simulate' if simulate else 'evaluate'}")
        if not resource:
            # list decisions
            data = await self._request("GET", "/api/v1/ai/policies/decisions", verbose=verbose)
            if data is None:
                return None
            if as_json:
                _print_json(data)
                return data
            count = data.get("count", len(data.get("decisions", [])) if isinstance(data, dict) else 0)
            print(f"\n{_bold(f'Policy decisions ({count})')}\n")
            _print_json(data)
            return data
        payload: dict[str, Any] = {"resource": resource, "context": context or {}}
        path = "/api/v1/ai/policies/simulate" if simulate else "/api/v1/ai/policies/evaluate"
        data = await self._request("POST", path, json_body=payload, verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        decision = data.get("decision", data.get("verdict", ""))
        color = _green if decision == "ALLOW" else _red if decision == "DENY" else _yellow
        print(f"\n  {_bold('Decision:')} {color(str(decision))}")
        for k in ("reason", "matched_policy", "matched_policies", "policy_version"):
            if k in data and data[k]:
                _print_info(f"  {k}: {data[k]}")
        print()
        _print_success("Policy evaluated")
        return data

    # -- risk -----------------------------------------------------------------

    async def risk(
        self,
        system: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header("risk")
        params: dict[str, Any] = {}
        if system:
            params["system"] = system
        data = await self._request("GET", "/api/v1/ai/risks", params=params, verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        items = data if isinstance(data, list) else data.get("risks", data.get("results", []))
        if isinstance(items, list):
            print(f"\n{_bold(f'Risks ({len(items)})')}\n")
            for i, r in enumerate(items, 1):
                if isinstance(r, dict):
                    rid = r.get("risk_id", r.get("id", "unknown"))
                    sev = r.get("severity", "")
                    sys_name = r.get("system", "")
                    color = _red if sev in ("CRITICAL", "HIGH") else _yellow if sev == "MEDIUM" else _cyan
                    print(f"  {_bold(f'{i}.')} {_cyan(str(rid))} {_dim(str(sys_name))} {color(str(sev))} score={r.get('score','')}")
                else:
                    print(f"  {i}. {r}")
            print()
        else:
            _print_json(data)
        _print_success("Risks retrieved")
        return data

    # -- status ---------------------------------------------------------------

    async def status(
        self,
        model_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        _print_header("status")
        if model_id:
            # monitoring snapshots for model
            data = await self._request("GET", f"/api/v1/ai/monitoring/{model_id}", verbose=verbose)
            if data is None:
                # fallback to model detail
                data = await self._request("GET", f"/api/v1/ai/models/{model_id}", verbose=verbose)
        else:
            # list models as status overview
            data = await self._request("GET", "/api/v1/ai/models", verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
            return data
        if isinstance(data, list):
            print(f"\n{_bold(f'Status overview ({len(data)})')}\n")
            for i, m in enumerate(data, 1):
                if isinstance(m, dict):
                    mid = m.get("id", m.get("model_id", ""))
                    name = m.get("name", mid)
                    st = m.get("status", m.get("availability", ""))
                    color = _green if st in ("ACTIVE", "AVAILABLE", "APPROVED", "healthy") else _yellow
                    print(f"  {_bold(f'{i}.')} {_cyan(str(name))} {_dim(str(mid))} {color(str(st))}")
                else:
                    print(f"  {i}. {m}")
            print()
        elif isinstance(data, dict):
            for k in ("status", "availability", "latency_ms", "error_rate", "quality", "safety", "drift_detected"):
                if k in data:
                    val = data[k]
                    _print_info(f"  {k}: {val}")
            if not any(k in data for k in ("status", "availability", "latency_ms")):
                for k, v in data.items():
                    if isinstance(v, (list, dict)):
                        _print_info(f"  {k}: ({type(v).__name__}, {len(v)} items)")
                    else:
                        _print_info(f"  {k}: {v}")
        _print_success("Status retrieved")
        return data


# ---------------------------------------------------------------------------
# Parser & dispatcher
# ---------------------------------------------------------------------------


def build_aiml_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nova ai",
        description="NovaForge AIML CLI — models, providers, prompts, evaluate, approve, deploy, rollback, policy, risk, status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", default=None, dest="base_url", help="Backend base URL (default: NOVAFORGE_API_URL or http://localhost:8000)")
    parser.add_argument("--base", default=None, dest="base", help="Alias for --base-url")
    parser.add_argument("--tenant", default=None, help="Tenant id override")
    parser.add_argument("--token", default=None, help="Bearer token (default: NOVAFORGE_TOKEN)")
    parser.add_argument("--api-key", default=None, dest="api_key", help="API key")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    parser.add_argument("--ci", action="store_true", help="CI mode (machine-readable, non-zero exit on failure)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # models
    p_models = sub.add_parser("models", help="List or get models")
    p_models.add_argument("--provider", default=None, help="Filter by provider")
    p_models.add_argument("--status", default=None, help="Filter by status")
    p_models.add_argument("--model-id", default=None, dest="model_id", help="Get single model by id")

    # providers
    p_providers = sub.add_parser("providers", help="List or get providers")
    p_providers.add_argument("--provider", default=None, dest="provider", help="Provider key to fetch single provider")
    p_providers.add_argument("--check", default=None, help="Provider to check compliance for")

    # prompts
    p_prompts = sub.add_parser("prompts", help="List or get prompts")
    p_prompts.add_argument("--prompt-id", default=None, dest="prompt_id", help="Prompt id to fetch")
    p_prompts.add_argument("--classification", default=None, help="Filter by classification")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate or compare evaluation runs")
    p_eval.add_argument("--suite-id", default=None, dest="suite_id", help="Suite id to list runs")
    p_eval.add_argument("--candidate", default=None, dest="candidate_run_id", help="Candidate run id for compare")
    p_eval.add_argument("--baseline", default=None, dest="baseline_run_id", help="Baseline run id for compare")

    # approve
    p_approve = sub.add_parser("approve", help="Decide approval")
    p_approve.add_argument("approval_id", help="Approval id")
    p_approve.add_argument("--approver", required=True, help="Approver identity")
    p_approve.add_argument("--decision", default="approved", help="Decision: approved/rejected/approve/reject/allow/deny")
    p_approve.add_argument("--reason", default=None, help="Reason for decision")

    # deploy
    p_deploy = sub.add_parser("deploy", help="Deploy a model")
    p_deploy.add_argument("model_id", help="Model id to deploy")
    p_deploy.add_argument("--environment", default="production", help="Target environment")
    p_deploy.add_argument("--version", default=None, help="Version to deploy")

    # rollback
    p_rollback = sub.add_parser("rollback", help="Rollback a deployment")
    p_rollback.add_argument("deployment_id", help="Deployment id to rollback")

    # policy
    p_policy = sub.add_parser("policy", help="Evaluate or simulate policy")
    p_policy.add_argument("--resource", default=None, help="Resource identifier to evaluate")
    p_policy.add_argument("--context", default=None, help="JSON context string or path to JSON file")
    p_policy.add_argument("--simulate", action="store_true", help="Simulate (dry-run) instead of evaluate")
    p_policy.add_argument("--list", action="store_true", dest="list_policies", help="List policy decisions")

    # risk
    p_risk = sub.add_parser("risk", help="List risks")
    p_risk.add_argument("--system", default=None, help="Filter by system")
    p_risk.add_argument("--severity", default=None, help="Filter by severity")
    p_risk.add_argument("--risk-id", default=None, dest="risk_id", help="Risk id to assess (status drill-down)")

    # status
    p_status = sub.add_parser("status", help="Show monitoring/model status")
    p_status.add_argument("--model-id", default=None, dest="model_id", help="Model id to show status for")

    return parser


def _resolve_base_url(provided: Optional[str], alias: Optional[str]) -> str:
    url = provided or alias or os.environ.get("NOVAFORGE_API_URL") or os.environ.get("NOVAFORGE_BASE_URL") or os.environ.get("BACKEND_URL") or "http://localhost:8000"
    return url.rstrip("/")


def _resolve_token(provided: Optional[str], api_key: Optional[str]) -> Optional[str]:
    return provided or api_key or os.environ.get("NOVAFORGE_TOKEN") or os.environ.get("NOVAFORGE_API_KEY") or os.environ.get("API_KEY")


def _parse_context(value: Optional[str]) -> dict:
    if not value:
        return {}
    candidate = value.strip()
    if os.path.isfile(candidate):
        with open(candidate, "r", encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(candidate)
    except Exception:
        # treat as key=value comma-separated
        out: dict[str, Any] = {}
        for part in candidate.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
            elif part.strip():
                out[part.strip()] = True
        return out


async def _dispatch(args: argparse.Namespace) -> Any:
    base_url = _resolve_base_url(args.base_url, args.base)
    token = _resolve_token(args.token, args.api_key)
    ci = bool(getattr(args, "ci", False))
    verbose = bool(getattr(args, "verbose", False))
    as_json = bool(getattr(args, "as_json", False))

    if verbose:
        _print_info(f"Server: {base_url}")
        _print_info(f"Command: {args.command}")

    cmds = AIMLCLICommands(base_url=base_url, api_key=token, ci=ci)

    if args.command == "models":
        if getattr(args, "model_id", None):
            # single get
            data = await cmds._request("GET", f"/api/v1/ai/models/{args.model_id}", verbose=verbose)
            if data is None:
                return None
            if as_json:
                _print_json(data)
            else:
                for k, v in data.items():
                    _print_info(f"  {k}: {v}")
            return data
        return await cmds.models(provider=args.provider, status=args.status, verbose=verbose, as_json=as_json)

    if args.command == "providers":
        # check flag
        if getattr(args, "check", None):
            data = await cmds._request("GET", f"/api/v1/ai/providers/{args.check}", verbose=verbose)
            if data is None:
                return None
            if as_json:
                _print_json(data)
            else:
                _print_json(data)
            return data
        provider = getattr(args, "provider", None)
        return await cmds.providers(provider=provider, verbose=verbose, as_json=as_json)

    if args.command == "prompts":
        prompt_id = getattr(args, "prompt_id", None)
        cls = getattr(args, "classification", None)
        if prompt_id:
            return await cmds.prompts(prompt_id=prompt_id, verbose=verbose, as_json=as_json)
        # list prompts, filter classification via query param manually
        if cls:
            data = await cmds._request("GET", "/api/v1/ai/prompts", params={"classification": cls}, verbose=verbose)
            if data is None:
                return None
            if as_json:
                _print_json(data)
            else:
                _print_json(data)
            return data
        return await cmds.prompts(verbose=verbose, as_json=as_json)

    if args.command == "evaluate":
        return await cmds.evaluate(
            suite_id=getattr(args, "suite_id", None),
            candidate_run_id=getattr(args, "candidate_run_id", None),
            baseline_run_id=getattr(args, "baseline_run_id", None),
            verbose=verbose,
            as_json=as_json,
        )

    if args.command == "approve":
        return await cmds.approve(
            approval_id=args.approval_id,
            approver=args.approver,
            decision=args.decision,
            verbose=verbose,
            as_json=as_json,
        )

    if args.command == "deploy":
        return await cmds.deploy(
            model_id=args.model_id,
            environment=args.environment,
            version=args.version,
            verbose=verbose,
            as_json=as_json,
        )

    if args.command == "rollback":
        return await cmds.rollback(deployment_id=args.deployment_id, verbose=verbose, as_json=as_json)

    if args.command == "policy":
        if getattr(args, "list_policies", False):
            return await cmds.policy(verbose=verbose, as_json=as_json)
        ctx = _parse_context(getattr(args, "context", None))
        return await cmds.policy(
            resource=getattr(args, "resource", None),
            context=ctx,
            simulate=bool(getattr(args, "simulate", False)),
            verbose=verbose,
            as_json=as_json,
        )

    if args.command == "risk":
        if getattr(args, "risk_id", None):
            # drill into single risk via assess endpoint
            rid = getattr(args, "risk_id")
            data = await cmds._request("GET", f"/api/v1/ai/risks", params={"risk_id": rid}, verbose=verbose)
            if data is None:
                return None
            if as_json:
                _print_json(data)
            else:
                _print_json(data)
            return data
        return await cmds.risk(system=getattr(args, "system", None), verbose=verbose, as_json=as_json)

    if args.command == "status":
        return await cmds.status(model_id=getattr(args, "model_id", None), verbose=verbose, as_json=as_json)

    _print_error(f"Unknown command: {args.command}")
    return None


def handle_aiml_command(argv: Optional[list[str]] = None) -> None:
    """Entry point for ``nova ai`` CLI — parses args and dispatches via httpx.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    parser = build_aiml_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0 if not args.ci else 1)

    try:
        import asyncio

        result = asyncio.run(_dispatch(args))
        if result is None:
            # failure path — ci mode returns non-zero
            if getattr(args, "ci", False):
                sys.exit(1)
            sys.exit(1)
        if getattr(args, "ci", False) and isinstance(result, dict) and result.get("verdict") in ("BLOCK", "FAIL", "DENY"):
            sys.exit(1)
    except KeyboardInterrupt:
        print(_yellow("\nInterrupted."))
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        _print_error(str(exc))
        sys.exit(1)


# backwards-compat alias used by some handlers
def aiml_cli_main(argv: Optional[list[str]] = None) -> None:
    return handle_aiml_command(argv)


if __name__ == "__main__":
    handle_aiml_command()
