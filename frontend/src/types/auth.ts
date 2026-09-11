export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "expired";

export interface SessionUser {
  id: string;
  email: string;
  username: string;
}

/** Backend permission strings (mirror of IAMPermission values). UX-only. */
export const PERMISSIONS = {
  orgRead: "organization:read",
  billingRead: "billing:read",
  billingAdmin: "billing:admin",
  auditRead: "audit:read",
  admin: "settings:admin",
  opsAdmin: "admin:all",
  secOpsRead: "secops:read",
  secOpsWrite: "secops:write",
  zeroTrustWrite: "zero_trust:write",
  dataWrite: "data:write",
  dataExport: "data:export",
  workflowExecute: "workflow:execute",
  repoRead: "repository:read",
  repoWrite: "repository:write",
  mlModelCreate: "aiml.model.create",
  mlModelUpdate: "aiml.model.update",
  mlModelVersion: "aiml.model.create_version",
  mlModelApprove: "aiml.model.approve",
  mlModelBlock: "aiml.model.block",
  mlProviderCreate: "aiml.provider.create",
  mlProviderUpdate: "aiml.provider.update",
  mlPromptCreate: "aiml.prompt.create",
  mlPromptVersion: "aiml.prompt.create_version",
  mlEvalCreate: "aiml.evaluation.create",
  mlEvalComplete: "aiml.evaluation.complete",
  mlGuardrailCreate: "aiml.guardrail.create",
  mlPolicyCreate: "aiml.policy.create",
  mlRiskCreate: "aiml.risk.create",
  mlRiskAssess: "aiml.risk.assess",
  mlCardCreate: "aiml.card.create",
  mlSystemCardCreate: "aiml.system_card.create",
  mlApprovalCreate: "aiml.approval.create",
  mlApprovalDecide: "aiml.approval.decide",
  mlGatewayInvoke: "aiml.gateway.invoke",
  mlMonitoringCreate: "aiml.monitoring.create",
  mlDeployCreate: "aiml.deployment.create",
  mlDeployRollback: "aiml.deployment.rollback",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];
