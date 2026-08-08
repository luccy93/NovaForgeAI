# NovaForge AI — Production Deployment Checklist
#
# Run through this checklist before every production deployment.

## Pre-Deployment
- [ ] All tests passing (backend + frontend)
- [ ] Lint/format checks passing
- [ ] Type checking passing
- [ ] Security scan completed (no critical findings)
- [ ] Migrations reviewed and tested
- [ ] Changelog updated
- [ ] Version bumped (semver)

## Infrastructure
- [ ] Secrets configured in cloud secret manager
- [ ] Database backups available (within 24h)
- [ ] Redis persistence enabled
- [ ] Neo4j backups available
- [ ] Qdrant snapshots available
- [ ] TLS certificates valid (>30 days)
- [ ] Monitoring alerts configured
- [ ] Logging pipeline healthy
- [ ] Prometheus targets all UP
- [ ] Grafana dashboards verified

## Deployment
- [ ] Blue/green or canary strategy selected
- [ ] Rollback plan documented
- [ ] Feature flags verified
- [ ] Database migrations applied (no conflicts)
- [ ] Canary deployed (10% traffic)
- [ ] Smoke tests passing on canary
- [ ] Rollout to 50% traffic
- [ ] Full rollout (100% traffic)
- [ ] Post-deployment smoke tests passing

## Post-Deployment
- [ ] Health checks all passing (/live, /ready, /health)
- [ ] Error rates normal (no increase)
- [ ] Latency within SLA
- [ ] Database connections stable
- [ ] Queue depth stable
- [ ] Memory usage within limits
- [ ] CPU usage within limits
- [ ] No security alerts
- [ ] Backup job completed successfully

## Rollback Triggers
If any of the following occur after deployment:
- Error rate increases > 5%
- p99 latency increases > 50%
- Database connection errors
- Health check failures
- Security alert (critical)

Execute rollback immediately:
```bash
kubectl rollout undo deployment/backend
kubectl rollout undo deployment/frontend
kubectl rollout undo deployment/worker
```

## Monitoring URLs
- Grafana: https://grafana.novaforge.ai
- Prometheus: https://prometheus.novaforge.ai
- Flower (Celery): https://flower.novaforge.ai
- Health: https://api.novaforge.ai/health
- Readiness: https://api.novaforge.ai/health/ready

## On-Call
- Primary: @sre-primary
- Secondary: @sre-secondary
- Escalation: @infra-lead
