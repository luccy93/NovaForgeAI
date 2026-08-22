"""Policy tester — dry-run policy evaluation and authorization explanation."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.iam.rbac_engine import rbac_engine
from app.iam.abac_engine import abac_engine
from app.iam.policy_authorizer import policy_authorizer


class PolicyTester:
    def __init__(self):
        self._test_results: list[dict] = []

    def test_rbac(self, role: str, permission: str, denied_permissions: Optional[list[str]] = None, inherited_roles: Optional[list[str]] = None) -> dict:
        result = rbac_engine.evaluate_access(role, permission, denied_permissions, inherited_roles)
        test = {"test_type": "rbac", "role": role, "permission": permission, "denied_permissions": denied_permissions or [], "inherited_roles": inherited_roles or [], "result": result, "tested_at": datetime.now(timezone.utc).isoformat()}
        self._test_results.append(test)
        return test

    def test_abac(self, resource_type: str, action: str, context: dict) -> dict:
        result = abac_engine.simulate(resource_type, action, context)
        test = {"test_type": "abac", "resource_type": resource_type, "action": action, "context": context, "result": result, "tested_at": datetime.now(timezone.utc).isoformat()}
        self._test_results.append(test)
        return test

    def test_full_authorization(self, user_id: str, org_id: str, permission: str, resource_type: str = "", resource_id: str = "", context: Optional[dict] = None) -> dict:
        result = policy_authorizer.authorize(user_id, org_id, permission, resource_type, resource_id, context)
        test = {"test_type": "full_authorization", "user_id": user_id, "org_id": org_id, "permission": permission, "resource_type": resource_type, "resource_id": resource_id, "context": context or {}, "result": result, "tested_at": datetime.now(timezone.utc).isoformat()}
        self._test_results.append(test)
        return test

    def simulate_access(self, org_id: str, scenario_name: str, user_role: str, permission: str, context: Optional[dict] = None, denied_permissions: Optional[list[str]] = None) -> dict:
        rbac_result = rbac_engine.evaluate_access(user_role, permission, denied_permissions)
        ctx = context or {}
        abac_result = None
        resource_type = ctx.get("resource_type", "")
        if resource_type:
            abac_result = abac_engine.simulate(resource_type, permission, ctx)
        decision = "allow" if rbac_result["allowed"] else "deny"
        if abac_result and abac_result.get("decision") == "denied":
            decision = "deny"
        elif abac_result and abac_result.get("decision") == "require_approval":
            decision = "require_approval"
        result = {"scenario_name": scenario_name, "org_id": org_id, "user_role": user_role, "permission": permission, "context": ctx, "rbac_result": rbac_result, "abac_result": abac_result, "final_decision": decision, "requires_approval": decision == "require_approval", "reason": rbac_result.get("reason", "")}
        self._test_results.append({"test_type": "simulation", "result": result, "tested_at": datetime.now(timezone.utc).isoformat()})
        return result

    def explain_decision(self, user_id: str, org_id: str, permission: str, context: Optional[dict] = None) -> dict:
        explanation = policy_authorizer.explain(user_id, org_id, permission, context)
        explanation["tested_at"] = datetime.now(timezone.utc).isoformat()
        self._test_results.append({"test_type": "explanation", "result": explanation})
        return explanation

    def batch_test(self, tests: list[dict]) -> dict:
        results = []
        passed = 0
        failed = 0
        for test in tests:
            test_type = test.get("test_type", "rbac")
            if test_type == "rbac":
                result = self.test_rbac(test["role"], test["permission"], test.get("denied_permissions"), test.get("inherited_roles"))
            elif test_type == "abac":
                result = self.test_abac(test["resource_type"], test["action"], test["context"])
            elif test_type == "full":
                result = self.test_full_authorization(test["user_id"], test["org_id"], test["permission"], test.get("resource_type", ""), test.get("resource_id", ""), test.get("context"))
            elif test_type == "simulation":
                result = self.simulate_access(test.get("org_id", ""), test.get("scenario_name", ""), test["role"], test["permission"], test.get("context"), test.get("denied_permissions"))
            else:
                result = {"error": f"Unknown test type: {test_type}"}
            expected = test.get("expected_decision")
            actual_decision = result.get("result", {}).get("decision") or result.get("result", {}).get("final_decision")
            match = actual_decision == expected if expected else True
            if match:
                passed += 1
            else:
                failed += 1
            results.append({"test": test, "result": result, "expected": expected, "actual": actual_decision, "passed": match})
        return {"total": len(tests), "passed": passed, "failed": failed, "results": results}

    def get_test_results(self, limit: int = 100) -> list[dict]:
        return self._test_results[-limit:]

    def get_stats(self) -> dict:
        return {"total_tests": len(self._test_results)}


policy_tester = PolicyTester()
