# Documentation Index

Welcome to the MCP Search Hub documentation! This directory contains comprehensive guides and references for using and developing MCP Search Hub.

## 📖 User Documentation

Start here if you're new to MCP Search Hub or want to use it in your projects:

- **[Getting Started](users/getting-started.md)** - Complete setup guide and first steps
- **[Quick Start Guide](users/quick-start.md)** - Fast track to basic usage
- **[Claude Desktop Setup](users/claude-desktop-setup.md)** - Claude Desktop integration guide
- **[STDIO Integration](users/stdio-integration.md)** - STDIO transport configuration

## 🛠️ Developer Documentation

Resources for contributors and developers working on MCP Search Hub:

- **[Contributing](developers/contributing.md)** - How to contribute to the project
- **[Development Guide](developers/development.md)** - Development workflows and practices
- **[API Reference](developers/api-reference.md)** - Complete tool and endpoint documentation
- **[Architectural Patterns](developers/architectural-patterns.md)** - Code patterns and standards
- **[Service Interfaces](developers/service-interfaces.md)** - Interface design guidelines
- **[Provider Architecture](developers/provider-architecture.md)** - Provider implementation guide
- **[Provider Management](developers/provider-management.md)** - Managing provider integrations
- **[OpenAPI Documentation](developers/openapi.md)** - API schema and specifications
- **[Coverage Report](developers/coverage-report.md)** - Test coverage analysis

## 🏗️ Architecture & Design

In-depth documentation about the system design and architecture:

- **[Architecture Overview](architecture/overview.md)** - High-level system design
- **[Caching Strategy](architecture/caching.md)** - Multi-tier caching implementation
- **[Tiered Caching](architecture/tiered-caching.md)** - Advanced caching patterns
- **[Error Handling](architecture/error-handling.md)** - Error patterns and recovery
- **[Middleware](architecture/middleware.md)** - Cross-cutting concerns
- **[LLM Routing](architecture/llm-routing.md)** - LLM-directed query routing
- **[Multi-Server Architecture](architecture/multi-server.md)** - Multi-server deployment patterns
- **[Retry Patterns](architecture/retry-patterns.md)** - Retry and resilience patterns

## 🚀 Operations & Deployment

Guides for deploying and operating MCP Search Hub:

- **[Configuration Guide](operators/configuration.md)** - Detailed configuration reference
- **[Configuration Standards](operators/configuration-standards.md)** - Configuration best practices
- **[Production Setup](operators/production-setup.md)** - Production deployment guide
- **[Docker Configuration](operators/docker.md)** - Container deployment guide

## 🔧 Troubleshooting

Common issues and solutions:

- **[Common Issues](troubleshooting/common-issues.md)** - Solutions to frequently encountered problems

## 📋 Architecture Decision Records (ADRs)

Documented architectural decisions and their rationale:

- **[ADR-001: Provider Integration Architecture](adrs/001-provider-integration-architecture.md)**
- **[ADR-002: Routing System Design](adrs/002-routing-system-design.md)**
- **[ADR-003: Caching Implementation](adrs/003-caching-implementation.md)**
- **[ADR-004: Middleware Architecture](adrs/004-middleware-architecture.md)**
- **[ADR-005: Provider Selection Strategy](adrs/005-provider-selection-strategy.md)**
- **[ADR-006: Embedding Official MCP Servers](adrs/006-embedding-official-mcp-servers.md)**

## 🧭 Quick Navigation

### By User Type

**🆕 New Users**
1. [Getting Started](users/getting-started.md)
2. [Configuration Guide](operators/configuration.md)
3. [Claude Desktop Setup](users/claude-desktop-setup.md)

**👩‍💻 Developers**
1. [Contributing](developers/contributing.md)
2. [Development Guide](developers/development.md)
3. [Architecture Overview](architecture/overview.md)

**🔧 DevOps/Administrators**
1. [Production Setup](operators/production-setup.md)
2. [Docker Configuration](operators/docker.md)
3. [Configuration Guide](operators/configuration.md)

**🐛 Troubleshooting**
1. [Common Issues](troubleshooting/common-issues.md)

### By Topic

**Search & Providers**
- [Provider Architecture](developers/provider-architecture.md)
- [Provider Management](developers/provider-management.md)
- [LLM Routing](architecture/llm-routing.md)

**Performance & Scaling**
- [Caching Strategy](architecture/caching.md)
- [Tiered Caching](architecture/tiered-caching.md)
- [Retry Patterns](architecture/retry-patterns.md)

**Integration & Development**
- [API Reference](developers/api-reference.md)
- [Service Interfaces](developers/service-interfaces.md)
- [Architectural Patterns](developers/architectural-patterns.md)

---

## 📄 Document Status

| Category | Status | Last Updated |
|----------|--------|--------------|
| User Documentation | ✅ Complete | 2024-01-15 |
| Developer Documentation | ✅ Complete | 2024-01-15 |
| Architecture Documentation | ✅ Complete | 2024-01-15 |
| Operations Documentation | ✅ Complete | 2024-01-15 |

> 💡 **Tip**: Use your browser's search (Ctrl/Cmd+F) to quickly find specific topics across all documentation.

## 🤝 Contributing to Documentation

Found an issue or want to improve the documentation? See our [Contributing Guide](developers/contributing.md#documentation) for information on how to help improve these docs.

Documentation follows the [Diátaxis framework](https://diataxis.fr/) for systematic organization:
- **Tutorials** (learning-oriented): Getting Started guides
- **How-to guides** (problem-oriented): Configuration and deployment guides  
- **Reference** (information-oriented): API docs and technical references
- **Explanation** (understanding-oriented): Architecture and design docs

---