# Operator Documentation

Welcome to the MCP Search Hub operator documentation. This section is for system administrators, DevOps engineers, and others responsible for deploying, configuring, and maintaining MCP Search Hub in production.

## Quick Navigation

### Deployment
- [Docker Deployment](/docs/docker-configuration.md) - Container-based deployment
- [Production Setup](/docs/operators/production-setup.md) - Production deployment guide
- [Kubernetes Deployment](/docs/operators/kubernetes.md) - K8s deployment manifests
- [Cloud Deployment](/docs/operators/cloud-deployment.md) - AWS, GCP, Azure guides

### Configuration
- [Environment Configuration](../../CONFIGURATION.md) - Complete configuration reference
- [Security Configuration](/docs/operators/security.md) - API keys, authentication, TLS
- [Provider Configuration](/docs/operators/provider-config.md) - Provider-specific settings
- [Performance Tuning](/docs/operators/performance-tuning.md) - Optimization settings

### Operations
- [Monitoring & Metrics](/docs/operators/monitoring.md) - Health checks, metrics endpoints
- [Logging Configuration](/docs/operators/logging.md) - Log levels, aggregation, analysis
- [Backup & Recovery](/docs/operators/backup.md) - Data persistence strategies
- [Scaling Guide](/docs/operators/scaling.md) - Horizontal and vertical scaling

### Maintenance
- [Upgrade Procedures](/docs/operators/upgrades.md) - Safe upgrade processes
- [Troubleshooting Guide](/docs/troubleshooting/common-issues.md) - Operational issues
- [Health Checks](/docs/operators/health-checks.md) - Monitoring system health
- [Incident Response](/docs/operators/incident-response.md) - Handling production issues

## Key Operational Guides

### Infrastructure Requirements
- [System Requirements](/docs/operators/requirements.md) - CPU, memory, storage needs
- [Network Configuration](/docs/operators/networking.md) - Ports, firewalls, load balancing
- [Provider Dependencies](/docs/operators/dependencies.md) - External service requirements

### Cost Management
- [Provider Cost Analysis](/docs/operators/cost-analysis.md) - Understanding provider costs
- [Budget Controls](/docs/operators/budget-controls.md) - Setting spending limits
- [Usage Monitoring](/docs/operators/usage-monitoring.md) - Tracking API usage

### Compliance & Security
- [Security Best Practices](/docs/operators/security-best-practices.md)
- [Compliance Guidelines](/docs/operators/compliance.md) - GDPR, SOC2, etc.
- [Audit Logging](/docs/operators/audit-logging.md) - Compliance logging
- [Data Retention](/docs/operators/data-retention.md) - Cache and log retention

## Production Checklist

Before deploying to production, ensure you have:

- [ ] Configured all required API keys
- [ ] Set up monitoring and alerting
- [ ] Configured appropriate resource limits
- [ ] Implemented backup strategies
- [ ] Tested failover procedures
- [ ] Documented runbooks
- [ ] Set up log aggregation
- [ ] Configured security policies

## Quick References

### Common Commands
```bash
# Health check
curl http://localhost:8000/health

# View metrics
curl http://localhost:8000/metrics

# Check provider status
curl http://localhost:8000/providers/status
```

### Environment Variables
See [Configuration Reference](../../CONFIGURATION.md) for complete list.

### Support Channels
- [Operations Issues](https://github.com/yourusername/mcp-search-hub/issues)
- [Security Concerns](mailto:security@example.com)
- [Community Support](https://github.com/yourusername/mcp-search-hub/discussions)