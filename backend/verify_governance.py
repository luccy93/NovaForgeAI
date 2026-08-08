"""Enterprise Governance & Policy Engine — live smoke test of all 12 modules."""
import os, sys, uuid, json, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from app.governance import *
ok = []

tmp = tempfile.mkdtemp()
print("=== Enterprise Governance & Policy Engine Verification ===\n")

# 1. Policy Engine
pe = PolicyEngine(os.path.join(tmp, "policies"))
policy = pe.create_policy(Policy(id=str(uuid.uuid4()), org_id="org-1", name="No Secrets in Prompts", type=PolicyType.AI_USAGE, effect=PolicyEffect.DENY, severity=PolicySeverity.HIGH, constraints=[PolicyConstraint(field="prompt", operator=ConstraintOperator.CONTAINS, value="sk-"), PolicyConstraint(field="model", operator=ConstraintOperator.IN, value=["gpt-4", "claude-3"])], actions=[PolicyAction(action_type="log", params={"level": "warn"})], priority=10, tags=["security", "ai"], version="1.0.0", status=PolicyStatus.ACTIVE, created_by="admin"))
pe.create_policy_version(policy.id, "admin")
result = pe.evaluate_policy(policy, {"prompt": "Use api key sk-abc123", "model": "gpt-4"})
enforce = pe.evaluate_and_enforce("org-1", PolicyType.AI_USAGE, {"prompt": "Use api key sk-abc123", "model": "gpt-4"})
sim = pe.simulate_policy("org-1", "test-sim", [policy.id], {"prompt": "Hello", "model": "gpt-4"})
test = pe.test_policy(policy.id, [{"context": {"prompt": "test sk-key", "model": "gpt-4"}, "expected_match": True}])
stats = pe.get_policy_stats("org-1")
ok.append(f"policies={len(pe.list_policies('org-1'))}, matched={result.matched}, decision={enforce['decision']}, sim_passed={sim.total_passed}, test_ok={test['passed']}")

# 2. Approval Workflows
awe = ApprovalWorkflowEngine(os.path.join(tmp, "approvals"))
wf = awe.create_workflow(ApprovalWorkflow(id=str(uuid.uuid4()), org_id="org-1", name="Deploy Approval", type=ApprovalType.MULTI_LEVEL, target_type="deployment", target_id="dep-1", steps=[ApprovalStep(id=str(uuid.uuid4()), name="Team Lead", role=ApprovalRole.APPROVER, required_approvers=1, order=1, wait_for_previous=True, timeout_hours=24, escalation_after_hours=48, status=ApprovalStatus.PENDING), ApprovalStep(id=str(uuid.uuid4()), name="Security", role=ApprovalRole.SECURITY_OFFICER, required_approvers=1, order=2, wait_for_previous=True, timeout_hours=48, escalation_after_hours=72, status=ApprovalStatus.PENDING)], status=ApprovalStatus.PENDING, current_step=0, initiated_by="dev-1"))
req = awe.submit_request(ApprovalRequest(id=str(uuid.uuid4()), workflow_id=wf.id, org_id="org-1", requester="dev-1", target_type="deployment", target_id="dep-1", reason="Production deploy", priority=NotificationPriority.HIGH, status=ApprovalStatus.PENDING))
awe.approve_step(wf.id, wf.steps[0].id, "lead-1")
pending = awe.get_pending_requests("lead-1", ApprovalRole.APPROVER)
metrics = awe.calculate_approval_metrics("org-1")
ok.append(f"workflows={len(awe.list_workflows('org-1'))}, step1_status={wf.steps[0].status.value}, pending={len(pending)}, approval_rate={metrics.get('approval_rate', 0):.0%}")

# 3. Change Management
cm = ChangeManager(os.path.join(tmp, "changes"))
change = cm.record_change(ChangeRecord(id=str(uuid.uuid4()), org_id="org-1", workspace_id="ws-1", entity=ChangeEntity.POLICY, entity_id=policy.id, change_type=ChangeType.UPDATE, severity=ChangeSeverity.MEDIUM, status=ChangeStatus.COMPLETED, source=ChangeSource.MANUAL, title="Update policy", description="Updated constraint", before_snapshot={"version": "1.0"}, after_snapshot={"version": "1.1"}, diff_summary="Changed version", initiated_by="admin"))
creq = cm.create_change_request(ChangeRequest(id=str(uuid.uuid4()), org_id="org-1", title="Update all policies", description="Bulk update", changes=[change], reason="Security", impact_analysis="Low", rollback_plan="Revert versions", risk_assessment="Low", status=ChangeStatus.APPROVED, severity=ChangeSeverity.MEDIUM, requester="admin"))
window = cm.create_change_window(ChangeWindow(id=str(uuid.uuid4()), org_id="org-1", name="Maintenance Window", start_time="2025-01-01T00:00:00Z", end_time="2025-12-31T23:59:59Z", allowed_change_types=[ChangeType.UPDATE], max_severity=ChangeSeverity.CRITICAL, is_active=True, created_by="admin"))
history = cm.get_change_history(ChangeEntity.POLICY, policy.id)
ok.append(f"changes={len(cm.list_changes('org-1'))}, creq_status={creq.status.value}, in_window={cm.is_in_change_window(ChangeType.UPDATE, ChangeSeverity.LOW)}, history={len(history)}")

# 4. Compliance Frameworks
cf = ComplianceManager(os.path.join(tmp, "compliance"))
control = cf.register_control(ComplianceControl(id=str(uuid.uuid4()), org_id="org-1", framework=ComplianceFramework.SOC2, control_id="CC-1", name="Access Control", description="Restrict access", category="Security", severity=ComplianceSeverity.HIGH, status=ComplianceControlStatus.IMPLEMENTED, owner="admin", implementation_details="RBAC enabled"))
assessment = cf.run_assessment("org-1", ComplianceFramework.SOC2, "auditor")
report = cf.generate_compliance_report("org-1", ComplianceFramework.SOC2, "2025-01-01", "2025-12-31")
score = cf.get_compliance_score("org-1", ComplianceFramework.SOC2)
mapping = cf.map_frameworks(ComplianceFramework.SOC2, ComplianceFramework.ISO_27001)
ok.append(f"controls={len(cf.list_controls('org-1'))}, score={score:.0%}, mappings={len(mapping.control_mappings)}")

# 5. Governance Dashboards
gdm = GovernanceDashboardManager(os.path.join(tmp, "gov_dashboards"))
config = gdm.create_dashboard_config(GovernanceDashboardConfig(id=str(uuid.uuid4()), org_id="org-1", name="Executive Governance", view=DashboardView.EXECUTIVE_SUMMARY, time_range=DashboardTimeRange.LAST_30D, chart_metrics=[ChartMetric.POLICY_COUNT, ChartMetric.COMPLIANCE_SCORE], is_active=True, created_by="admin"))
dash_data = gdm.get_dashboard_data(config.id)
violations = gdm.get_policy_violation_summary("org-1", 30)
overview = gdm.get_governance_overview("org-1")
exec_summary = gdm.get_executive_summary("org-1")
ok.append(f"dash_metrics={len(dash_data.metric_cards)}, violations={violations.total_violations}, policies={overview.active_policies}")

# 6. Risk Management
rm = RiskManager(os.path.join(tmp, "risks"))
factor = rm.register_risk_factor(RiskFactor(id=str(uuid.uuid4()), org_id="org-1", category=RiskCategory.SECURITY, name="Secret Exposure", weight=0.3, current_score=45.0, baseline_score=60.0, target_score=20.0, trend=RiskTrend.IMPROVING, owner="sec-team"))
assessment_risk = rm.run_risk_assessment("org-1", "auditor")
mitigation = rm.create_mitigation(RiskMitigation(id=str(uuid.uuid4()), risk_factor_id=factor.id, title="Implement secret scanner", action_plan="Deploy scanner", owner="sec-team", status=MitigationStatus.IN_PROGRESS, target_date="2025-06-01", effectiveness_score=0.0, cost=5000.0))
scorecard = rm.get_risk_scorecard("org-1")
report_risk = rm.generate_risk_report("org-1", "2025-01-01", "2025-12-31")
ok.append(f"factors={len(rm.list_risk_factors('org-1'))}, risk_score={assessment_risk.overall_score:.1f}, mitigations={len(rm.list_mitigations())}")

# 7. Audit Engine
ae = AuditEngine(os.path.join(tmp, "audit"))
event = ae.record_event(AuditEvent(id=str(uuid.uuid4()), org_id="org-1", workspace_id="ws-1", event_type=AuditEventType.POLICY_DECISION, severity=AuditSeverity.INFO, status=AuditStatus.SUCCESS, action="evaluate", resource_type="policy", resource_id=policy.id, actor_id="admin", actor_type="user", source_ip="10.0.0.1", user_agent="test", session_id="sess-1", request_id="req-1", changes={"effect": "deny"}, metadata={"reason": "secret detected"}))
ae.record_event(AuditEvent(id=str(uuid.uuid4()), org_id="org-1", workspace_id="ws-1", event_type=AuditEventType.AUTHENTICATION, severity=AuditSeverity.WARNING, status=AuditStatus.FAILURE, action="login", resource_type="session", resource_id="sess-2", actor_id="user-2", actor_type="user", source_ip="10.0.0.2", user_agent="test", session_id="sess-2", request_id="req-2", changes={}, metadata={"reason": "invalid password"}))
trail = ae.get_entity_trail("policy", policy.id)
recent = ae.get_recent_events("org-1", 10)
stats_audit = ae.get_event_stats("org-1", 30)
export = ae.export_audit_log("org-1", "2025-01-01", "2025-12-31", [AuditEventType.POLICY_DECISION, AuditEventType.AUTHENTICATION])
ok.append(f"events={len(ae.search_events('org-1'))}, trail_count={trail.event_count}, recent={len(recent)}, export_rows={export.record_count}")

# 8. Data Governance
dgm = DataGovernanceManager(os.path.join(tmp, "data_gov"))
asset = dgm.register_asset(DataAsset(id=str(uuid.uuid4()), org_id="org-1", name="Customer DB", category=DataCategory.PII, classification=DataClassification.RESTRICTED, owner="dpo", location="/data/customers", format="postgresql", size_bytes=1e9, retention_days=365, retention_action=RetentionAction.ARCHIVE, tags=["pii", "customer"]))
lineage = dgm.record_lineage(DataLineageEntry(id=str(uuid.uuid4()), asset_id=asset.id, source_asset_id="raw-import", transformation="ETL", state=DataState.STORED, timestamp="2025-01-01T00:00:00Z", actor="etl-pipeline", description="Imported from source"))
retention_policy = dgm.create_retention_policy(DataRetentionPolicy(id=str(uuid.uuid4()), org_id="org-1", name="PII Retention", category=DataCategory.PII, classification=DataClassification.RESTRICTED, retention_days=365, action=RetentionAction.ARCHIVE, enabled=True))
dg_report = dgm.get_data_governance_report("org-1", "2025-01-01", "2025-12-31")
dgm.classify_asset(asset.id, DataClassification.CONFIDENTIAL)
ok.append(f"assets={len(dgm.list_assets('org-1'))}, lineage={len(dgm.get_asset_lineage(asset.id))}, report_score={dg_report.compliance_score:.0%}")

# 9. Organization Controls
oc = OrganizationControls(os.path.join(tmp, "org_controls"))
control_org = oc.create_control(OrgControl(id=str(uuid.uuid4()), org_id="org-1", name="Production Access", control_type=ControlType.ENVIRONMENT_RESTRICTION, enabled=True, priority=1, constraints=[{"type": "role", "value": "admin"}], created_by="admin"))
iso_policy = oc.set_workspace_isolation(WorkspaceIsolationPolicy(id=str(uuid.uuid4()), org_id="org-1", workspace_id="ws-1", isolated=True, allowed_cross_workspace_access=[], data_isolation_level="strict", network_isolation="full", share_settings={}))
env_rule = oc.set_environment_rule(EnvironmentAccessRule(id=str(uuid.uuid4()), org_id="org-1", environment=EnvironmentType.PRODUCTION, allowed_roles=["admin"], allowed_users=[], require_approval=True, approval_roles=["security"], allowed_days=["Mon", "Tue", "Wed", "Thu", "Fri"], allowed_hours_start="09:00", allowed_hours_end="18:00", ip_restrictions=[]))
loc_res = oc.create_location_restriction(LocationRestriction(id=str(uuid.uuid4()), org_id="org-1", name="Block High Risk", allowed_countries=["US", "GB", "DE"], blocked_countries=["XX"], allowed_regions=[], allowed_ip_ranges=["10.0.0.0/8", "192.168.0.0/16"], block_proxy=True, action_on_violation="deny"))
time_access = oc.set_time_based_access(TimeBasedAccess(id=str(uuid.uuid4()), org_id="org-1", name="Contractor Hours", user_id="user-1", allowed_days=["Mon", "Tue", "Wed", "Thu", "Fri"], allowed_start_time="09:00", allowed_end_time="17:00", timezone="UTC", max_session_hours=8, expires_at="2025-12-31T23:59:59Z"))
env_check = oc.check_environment_access(EnvironmentType.PRODUCTION, "admin", "admin")
ip_check = oc.check_location_access("10.0.0.50", "US")
ok.append(f"controls={len(oc.list_controls('org-1'))}, env_access={env_check['allowed']}, ip_allowed={ip_check}")

# 10. AI Governance
agm = AIGovernanceManager(os.path.join(tmp, "ai_gov"))
ai_policy = agm.create_governance_policy(AIGovernancePolicy(id=str(uuid.uuid4()), org_id="org-1", name="Block Sensitive Models", domain=AIGovernanceDomain.MODEL, model_risk_level=ModelRiskLevel.HIGH, action=GovernanceAction.BLOCK, approval=ApprovalRequirement.EXECUTIVE_REVIEW, blocked_providers=["unknown-provider"], blocked_models=["gpt-4-32k"], max_tokens_per_request=32000, max_cost_per_request=0.50, require_audit_log=True, enabled=True))
eval_result = agm.evaluate_prompt("org-1", "Write code to access /etc/passwd", "gpt-4", "openai", 100, 0.05)
approval_model = agm.approve_model(ModelApprovalRecord(id=str(uuid.uuid4()), org_id="org-1", model_name="claude-3-opus", provider="anthropic", risk_level=ModelRiskLevel.LOW, status=ApprovalRequirement.APPROVER, requested_by="dev-1", approved_by="admin"))
model_check = agm.check_model_approval("claude-3-opus", "anthropic")
gov_report = agm.get_ai_governance_report("org-1", "2025-01-01", "2025-12-31")
ok.append(f"ai_policies={len(agm.list_policies('org-1'))}, eval_action={eval_result['action_taken'].value}, model_approved={model_check['approved']}")

# 11. Security Governance
sgm = SecurityGovernanceManager(os.path.join(tmp, "sec_gov"))
sec_policy = sgm.create_security_policy(SecurityPolicy(id=str(uuid.uuid4()), org_id="org-1", name="MFA Required", policy_type=SecurityPolicyType.MFA, enabled=True, priority=1, requirements={"required": True, "methods": ["totp"]}, created_by="admin"))
mfa_policy = sgm.set_mfa_policy(MfaPolicy(id=str(uuid.uuid4()), org_id="org-1", name="Corporate MFA", required=True, methods=[MfaMethod.TOTP, MfaMethod.PUSH_NOTIFICATION], grace_period_days=7, enforce_for_roles=["admin", "developer"], exempt_roles=["readonly"], remember_device_days=30))
pwd_policy = sgm.set_password_policy(PasswordPolicy(id=str(uuid.uuid4()), org_id="org-1", name="Corp Password Policy", complexity=PasswordComplexity.HIGH, min_length=12, max_length=64, require_uppercase=True, require_lowercase=True, require_numbers=True, require_special=True, expiry_days=90, prevent_reuse_count=10, max_login_attempts=5, lockout_duration_minutes=30))
pwd_valid = sgm.validate_password("org-1", "Test@12345678")
enc_policy = sgm.set_encryption_policy(EncryptionPolicy(id=str(uuid.uuid4()), org_id="org-1", name="Default Encryption", standard=EncryptionStandard.AES_256, key_rotation_days=365, encrypt_at_rest=True, encrypt_in_transit=True, encrypt_backups=True, key_vault_provider="aws-kms"))
incident = sgm.report_incident(SecurityIncident(id=str(uuid.uuid4()), org_id="org-1", incident_type="unauthorized_access", severity="high", title="Suspicious login", description="Multiple failed logins", affected_resources=["user-1", "workspace-1"], detected_at="2025-06-01T00:00:00Z", reported_by="system", status="open"))
sec_score = sgm.get_security_score("org-1")
ok.append(f"sec_policies={len(sgm.list_security_policies('org-1'))}, pwd_valid={pwd_valid['valid']}, incidents={len(sgm.list_incidents('org-1'))}, score={sec_score:.1f}")

# 12. Workflow Automation
wa = WorkflowAutomation(os.path.join(tmp, "automation"))
rule = wa.create_rule(AutomationRule(id=str(uuid.uuid4()), org_id="org-1", name="Alert on Policy Violation", trigger=AutomationTrigger.VIOLATION_DETECTED, match_type=TriggerMatchType.ALL, conditions=[{"field": "severity", "operator": ">=", "value": "high"}], actions=[AutomationAction.NOTIFY_STAKEHOLDERS, AutomationAction.ESCALATE_EVENT], action_params={"channel": "slack", "escalation_level": 1}, cooldown_minutes=60, enabled=True, created_by="admin"))
exec_result = wa.execute_rule(rule.id, {"severity": "critical", "violation": "secret_in_prompt"})
triggered = wa.process_trigger("org-1", AutomationTrigger.VIOLATION_DETECTED, {"severity": "high", "violation": "test"})
sched = wa.schedule_automation(AutomationSchedule(id=str(uuid.uuid4()), org_id="org-1", name="Weekly Compliance", trigger=AutomationTrigger.SCHEDULED, cron_expression="0 0 * * 0", actions=[AutomationAction.GENERATE_COMPLIANCE_REPORT], action_params={"framework": "SOC2"}, enabled=True, last_run="", next_run="2025-07-01T00:00:00Z"))
tmpl = wa.create_notification_template(NotificationTemplate(id=str(uuid.uuid4()), org_id="org-1", name="Violation Alert", trigger=AutomationTrigger.VIOLATION_DETECTED, subject="Policy Violation: {{violation}}", body="Severity: {{severity}}\nDetails: {{details}}", channels=["slack", "email"], variables=["violation", "severity", "details"]))
rendered = wa.render_notification(tmpl.id, {"violation": "secret_in_prompt", "severity": "high", "details": "API key detected"})
auto_report = wa.run_compliance_report_automation("org-1")
ok.append(f"rules={len(wa.list_rules('org-1'))}, exec_status={exec_result.status}, triggered={len(triggered)}, rendered_subj={rendered['subject']}")

print(f"\nAll {len(ok)}/12 modules verified successfully.")
for i, msg in enumerate(ok, 1):
    print(f"  {i:2d}. {msg}")
print("\nDone.")
