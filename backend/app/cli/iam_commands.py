"""IAM CLI commands."""
from __future__ import annotations
import json as json_mod


def handle_iam_command(args):
    if not args or args[0] == "help":
        _print_help()
        return
    json_out = "--json" in args
    args = [a for a in args if a != "--json"]
    dispatch = {
        "org": _org, "workspace": _ws, "project": _proj, "member": _member,
        "team": _team, "role": _role, "policy": _policy, "authorize": _authz,
        "explain": _explain, "session": _session, "api-key": _apikey,
        "service-account": _sa, "idp": _idp, "scim": _scim,
        "break-glass": _bg, "quota": _quota, "audit": _audit,
        "access-review": _ar, "privilege-analysis": _pa,
        "policy-test": _pt, "rate-limit": _rl,
    }
    h = dispatch.get(args[0])
    if h:
        h(args[1:], json_out)
    else:
        print(f"Unknown: {args[0]}")
        _print_help()


def _out(data, js, hdr=""):
    if js:
        print(json_mod.dumps(data, indent=2, default=str))
    elif hdr:
        print(f"\n{hdr}")
        if isinstance(data, list):
            for item in data:
                print(f"  - {item.get('name', item.get('id', item))}")
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
    else:
        print(json_mod.dumps(data, indent=2, default=str) if js else data)


def _print_help():
    print("nova iam: org|workspace|project|member|team|role|policy|authorize|explain|session|api-key|service-account|idp|scim|break-glass|quota|audit|access-review|privilege-analysis|policy-test|rate-limit|help")


def _org(a, js):
    from app.iam.organization_service import org_service
    from app.iam.membership_service import membership_service
    from app.iam.quota_service import quota_service
    from app.iam.audit_service import audit_service
    from app.iam.session_service import session_service
    if not a:
        print("Usage: nova iam org <list|create|get|stats|suspend|reactivate|delete>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(org_service.list_all(), js, "Organizations:")
    elif c == "create":
        org = org_service.create(r[0], r[1], r[2] if len(r) > 2 else "cli")
        membership_service.add_member(org["id"], org["owner_id"], "owner")
        quota_service.initialize_org_quotas(org["id"])
        _out(org, js, "Created:")
    elif c == "get":
        _out(org_service.get(r[0]) or {}, js)
    elif c == "stats":
        _out(org_service.get_stats(r[0]), js)
    elif c == "suspend":
        org_service.suspend(r[0], r[1] if len(r) > 1 else "")
        session_service.revoke_all_for_org(r[0])
        _out({"suspended": True}, js)
    elif c == "reactivate":
        org_service.reactivate(r[0])
        _out({"reactivated": True}, js)
    elif c == "delete":
        org_service.delete(r[0])
        audit_service.log_org_delete(r[0], "cli", r[1] if len(r) > 1 else "")
        _out({"deleted": True}, js)


def _ws(a, js):
    from app.iam.workspace_service import workspace_service
    if not a:
        print("Usage: nova iam workspace <list|create|get|delete>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(workspace_service.list_for_org(r[0]), js, "Workspaces:")
    elif c == "create":
        _out(workspace_service.create(r[0], r[1], r[2] if len(r) > 2 else r[1].lower()), js, "Created:")
    elif c == "get":
        _out(workspace_service.get(r[0]) or {}, js)
    elif c == "delete":
        workspace_service.delete(r[0])
        _out({"deleted": True}, js)


def _proj(a, js):
    from app.iam.project_service import project_service
    if not a:
        print("Usage: nova iam project <list|create|get|delete>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(project_service.list_for_workspace(r[0]), js, "Projects:")
    elif c == "create":
        _out(project_service.create(r[0], r[1], r[2], r[3] if len(r) > 3 else r[2].lower()), js, "Created:")
    elif c == "get":
        _out(project_service.get(r[0]) or {}, js)
    elif c == "delete":
        project_service.delete(r[0])
        _out({"deleted": True}, js)


def _member(a, js):
    from app.iam.membership_service import membership_service
    if not a:
        print("Usage: nova iam member <list|invite|role|remove|suspend|stats>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(membership_service.list_members(r[0]), js, "Members:")
    elif c == "invite":
        _out(membership_service.invite(r[0], r[1], r[2] if len(r) > 2 else "viewer"), js, "Invited:")
    elif c == "role":
        _out(membership_service.update_role(r[0], r[1], r[2]), js, "Role updated:")
    elif c == "remove":
        membership_service.remove_member(r[0], r[1])
        _out({"removed": True}, js)
    elif c == "suspend":
        membership_service.suspend_member(r[0], r[1])
        _out({"suspended": True}, js)
    elif c == "stats":
        _out(membership_service.get_stats(r[0]), js)


def _team(a, js):
    from app.iam.team_service import team_service
    if not a:
        print("Usage: nova iam team <list|create|delete|add-member|remove-member>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(team_service.list_for_org(r[0]), js, "Teams:")
    elif c == "create":
        _out(team_service.create(r[0], r[1]), js, "Created:")
    elif c == "delete":
        team_service.delete(r[0])
        _out({"deleted": True}, js)
    elif c == "add-member":
        _out(team_service.add_member(r[0], r[1], r[2] if len(r) > 2 else "member"), js)
    elif c == "remove-member":
        team_service.remove_member(r[0], r[1])
        _out({"removed": True}, js)


def _role(a, js):
    from app.iam.rbac_engine import rbac_engine
    if not a:
        print("Usage: nova iam role <list|create|hierarchy>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(rbac_engine.list_roles(r[0] if r else None), js, "Roles:")
    elif c == "create":
        perms = r[2].split(",") if len(r) > 2 else []
        _out(rbac_engine.create_custom_role(r[0], r[1], perms), js, "Created:")
    elif c == "hierarchy":
        _out(rbac_engine.get_role_hierarchy(r[0]), js)


def _policy(a, js):
    from app.iam.policy_authorizer import policy_authorizer
    if not a:
        print("Usage: nova iam policy <list|create|delete>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(policy_authorizer.list_resource_policies(r[0]), js, "Policies:")
    elif c == "create":
        _out(policy_authorizer.create_resource_policy(r[0], r[1]), js, "Created:")
    elif c == "delete":
        policy_authorizer.delete_resource_policy(r[0])
        _out({"deleted": True}, js)


def _authz(a, js):
    from app.iam.policy_authorizer import policy_authorizer
    if len(a) < 3:
        print("Usage: nova iam authorize <user_id> <org_id> <permission>")
        return
    _out(policy_authorizer.authorize(a[0], a[1], a[2]), js)


def _explain(a, js):
    from app.iam.policy_authorizer import policy_authorizer
    if len(a) < 3:
        print("Usage: nova iam explain <user_id> <org_id> <permission>")
        return
    _out(policy_authorizer.explain(a[0], a[1], a[2]), js)


def _session(a, js):
    from app.iam.session_service import session_service
    if not a:
        print("Usage: nova iam session <list|revoke|cleanup>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(session_service.list_for_user(r[0]) if r else [], js, "Sessions:")
    elif c == "revoke":
        session_service.revoke(r[0])
        _out({"revoked": True}, js)
    elif c == "cleanup":
        n = session_service.cleanup_expired()
        _out({"cleaned": n}, js)


def _apikey(a, js):
    from app.iam.api_key_service import api_key_service
    if not a:
        print("Usage: nova iam api-key <list|create|revoke|rotate|cleanup>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(api_key_service.list_for_org(r[0]) if r else [], js, "API Keys:")
    elif c == "create":
        result = api_key_service.create(r[0], r[1], r[2])
        _out(result, js, "Created:")
    elif c == "revoke":
        api_key_service.revoke(r[0])
        _out({"revoked": True}, js)
    elif c == "rotate":
        _out(api_key_service.rotate(r[0]), js)
    elif c == "cleanup":
        n = api_key_service.cleanup_expired()
        _out({"cleaned": n}, js)


def _sa(a, js):
    from app.iam.service_account_service import service_account_service
    if not a:
        print("Usage: nova iam service-account <list|create|rotate|disable|cleanup>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(service_account_service.list_for_org(r[0]) if r else [], js, "Service Accounts:")
    elif c == "create":
        _out(service_account_service.create(r[0], r[1]), js, "Created:")
    elif c == "rotate":
        _out(service_account_service.rotate(r[0]), js)
    elif c == "disable":
        service_account_service.disable(r[0])
        _out({"disabled": True}, js)
    elif c == "cleanup":
        n = service_account_service.cleanup_expired()
        _out({"cleaned": n}, js)


def _idp(a, js):
    from app.iam.identity_provider_service import identity_provider_service
    if not a:
        print("Usage: nova iam idp <list|create|validate>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(identity_provider_service.list_for_org(r[0]) if r else [], js, "Identity Providers:")
    elif c == "create":
        _out(identity_provider_service.create(r[0], r[1], r[2] if len(r) > 2 else "oidc"), js, "Created:")
    elif c == "validate":
        _out(identity_provider_service.validate_config(r[0]), js)


def _scim(a, js):
    from app.iam.scim_service import scim_service
    if not a:
        print("Usage: nova iam scim <list-dirs|create-dir|sync|list-users>")
        return
    c, r = a[0], a[1:]
    if c == "list-dirs":
        _out(scim_service.list_directories(r[0]) if r else [], js, "Directories:")
    elif c == "create-dir":
        _out(scim_service.create_directory(r[0], r[1], r[2] if len(r) > 2 else "generic"), js, "Created:")
    elif c == "sync":
        _out(scim_service.sync_directory(r[0]), js)
    elif c == "list-users":
        _out(scim_service.list_users(r[0] if r else None), js, "Users:")


def _bg(a, js):
    from app.iam.break_glass_service import break_glass_service
    if not a:
        print("Usage: nova iam break-glass <request|list|end>")
        return
    c, r = a[0], a[1:]
    if c == "request":
        _out(break_glass_service.request(r[0], r[1], r[2] if len(r) > 2 else "cli_emergency", mfa_verified=True), js, "Break-glass:")
    elif c == "list":
        _out(break_glass_service.list_active(r[0] if r else None), js, "Active:")
    elif c == "end":
        break_glass_service.end(r[0])
        _out({"ended": True}, js)


def _quota(a, js):
    from app.iam.quota_service import quota_service
    if not a:
        print("Usage: nova iam quota <list|update|summary|init>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(quota_service.get_all_quotas(r[0]) if r else [], js, "Quotas:")
    elif c == "update":
        _out(quota_service.update_quota(r[0], r[1], int(r[2])), js)
    elif c == "summary":
        _out(quota_service.get_usage_summary(r[0]) if r else {}, js)
    elif c == "init":
        _out(quota_service.initialize_org_quotas(r[0]) if r else [], js, "Initialized:")


def _audit(a, js):
    from app.iam.audit_service import audit_service
    if not a:
        print("Usage: nova iam audit <query|stats>")
        return
    c, r = a[0], a[1:]
    if c == "query":
        _out(audit_service.query(org_id=r[0] if r else None), js, "Audit Log:")
    elif c == "stats":
        _out(audit_service.get_stats(r[0] if r else None), js)


def _ar(a, js):
    from app.iam.access_review_service import access_review_service
    if not a:
        print("Usage: nova iam access-review <create|list>")
        return
    c, r = a[0], a[1:]
    if c == "create":
        _out(access_review_service.create_review(r[0], r[1] if len(r) > 1 else "periodic"), js, "Created:")
    elif c == "list":
        _out(access_review_service.list_reviews(r[0] if r else None), js, "Reviews:")


def _pa(a, js):
    from app.iam.privilege_analysis_service import privilege_analysis_service
    from app.iam.membership_service import membership_service
    from app.iam.service_account_service import service_account_service
    from app.iam.api_key_service import api_key_service
    from app.iam.policy_authorizer import policy_authorizer
    if not a:
        print("Usage: nova iam privilege-analysis run <org_id>")
        return
    if a[0] == "run" and len(a) > 1:
        org_id = a[1]
        mems = membership_service.list_members(org_id)
        sas = service_account_service.list_for_org(org_id, active_only=False)
        keys = api_key_service.list_for_org(org_id)
        policies = policy_authorizer.list_resource_policies(org_id)
        _out(privilege_analysis_service.run_full_analysis(org_id, mems, sas, keys, policies), js, "Analysis:")
    else:
        _out(privilege_analysis_service.get_analyses(a[0] if a else None), js, "Analyses:")


def _pt(a, js):
    from app.iam.policy_tester import policy_tester
    if not a:
        print("Usage: nova iam policy-test <rbac|abac>")
        return
    c, r = a[0], a[1:]
    if c == "rbac":
        _out(policy_tester.test_rbac(r[0], r[1]), js)
    elif c == "abac":
        import json as j
        _out(policy_tester.test_abac(r[0], r[1], j.loads(r[2]) if len(r) > 2 else {}), js)


def _rl(a, js):
    from app.iam.rate_limiter import rate_limiter
    _out(rate_limiter.get_stats(), js, "Rate Limiter Stats:")
