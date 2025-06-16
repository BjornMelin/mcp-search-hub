# Contributing to MCP Search Hub

Thank you for your interest in contributing to MCP Search Hub! This guide will help you get started with contributing to our intelligent multi-provider search aggregation server.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Contribution Guidelines](#contribution-guidelines)
- [Code Standards](#code-standards)
- [Testing Requirements](#testing-requirements)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Community Guidelines](#community-guidelines)

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Python 3.10+** (required for FastMCP 2.0)
- **Git** for version control
- **uv** for fast dependency management
- **Node.js 16+** (for provider MCP servers)
- Basic familiarity with:
  - FastMCP framework
  - Python async/await patterns
  - MCP (Model Context Protocol)

### Types of Contributions

We welcome various types of contributions:

- 🐛 **Bug fixes** - Fix issues and improve stability
- ✨ **Features** - Add new functionality and capabilities
- 📚 **Documentation** - Improve guides, references, and examples
- 🧪 **Tests** - Expand test coverage and quality
- 🎨 **Code quality** - Refactoring and optimization
- 🔧 **Provider integration** - Add new search providers
- 📊 **Performance** - Optimization and monitoring improvements

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/mcp-search-hub.git
cd mcp-search-hub

# Add upstream remote
git remote add upstream https://github.com/BjornMelin/mcp-search-hub.git
```

### 2. Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies with development tools
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### 3. Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Add your API keys for testing
# Note: You don't need all providers for development
LINKUP_API_KEY=your_test_key
EXA_API_KEY=your_test_key
```

### 4. Verify Setup

```bash
# Run tests to verify setup
uv run pytest

# Start the server
python -m mcp_search_hub.main

# Test in another terminal
curl http://localhost:8000/health
```

## Contribution Guidelines

### Before You Start

1. **Check existing issues** - Look for related discussions
2. **Create an issue** - Describe your planned contribution
3. **Discuss approach** - Get feedback before major changes
4. **Follow conventions** - Maintain consistency with existing code

### Branch Strategy

```bash
# Create feature branch from main
git checkout main
git pull upstream main
git checkout -b feature/your-feature-name

# For bug fixes
git checkout -b fix/issue-description

# For documentation
git checkout -b docs/topic-description
```

### Commit Messages

Follow conventional commit format:

```
type(scope): description

Longer description if needed.

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions/changes
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks

**Examples:**
```
feat(providers): add support for new search provider
fix(cache): resolve Redis connection timeout issue
docs(api): improve search tool documentation
test(integration): add end-to-end provider tests
```

## Code Standards

### Python Standards

We follow PEP 8 with some modifications enforced by `ruff`:

```bash
# Format code
ruff format .

# Lint and fix issues
ruff check --fix .

# Sort imports
ruff check --select I --fix .
```

### Code Quality Requirements

1. **Type Hints**: All functions must have type annotations
2. **Docstrings**: Public functions need docstrings
3. **Error Handling**: Proper exception handling with custom error types
4. **Async/Await**: Use async patterns consistently
5. **Logging**: Use structured logging with appropriate levels

### Example Code Style

```python
from typing import Dict, List, Optional
import logging

from .models import SearchQuery, SearchResult
from .errors import ProviderError

logger = logging.getLogger(__name__)


async def search_provider(
    query: SearchQuery,
    timeout: Optional[int] = None,
) -> List[SearchResult]:
    """
    Search using a specific provider.
    
    Args:
        query: The search query to execute
        timeout: Optional timeout in milliseconds
        
    Returns:
        List of search results
        
    Raises:
        ProviderError: If the provider request fails
    """
    try:
        logger.info(f"Searching with provider: {query.provider}")
        # Implementation here
        return results
    except Exception as e:
        logger.error(f"Provider search failed: {e}")
        raise ProviderError(f"Search failed: {e}") from e
```

### Architecture Patterns

1. **Provider Pattern**: All providers implement `SearchProvider` interface
2. **Generic MCP**: Use `GenericMCPProvider` for new MCP server integrations
3. **Configuration-Driven**: Add provider settings to `provider_config.py`
4. **Middleware Pattern**: Cross-cutting concerns use middleware
5. **Async First**: All I/O operations should be async

## Testing Requirements

### Test Coverage

- **Minimum 90% coverage** for new code
- **All public APIs** must have tests
- **Error conditions** must be tested
- **Integration tests** for provider interactions

### Test Types

```bash
# Unit tests
uv run pytest tests/test_*.py

# Integration tests
uv run pytest tests/test_*_integration.py

# End-to-end tests
uv run pytest tests/test_end_to_end.py

# Performance tests
uv run pytest tests/test_*_performance.py
```

### Writing Tests

Use pytest with async support:

```python
import pytest
from unittest.mock import AsyncMock, patch

from mcp_search_hub.providers.exa_mcp import ExaMCPProvider
from mcp_search_hub.models import SearchQuery


class TestExaMCPProvider:
    @pytest.fixture
    async def provider(self):
        """Create test provider instance."""
        provider = ExaMCPProvider()
        await provider.initialize()
        yield provider
        await provider.cleanup()

    async def test_search_success(self, provider):
        """Test successful search operation."""
        query = SearchQuery(query="test query", max_results=5)
        
        with patch.object(provider, '_execute_search') as mock_search:
            mock_search.return_value = [{"title": "Test", "url": "http://test.com"}]
            
            results = await provider.search(query)
            
            assert len(results) == 1
            assert results[0].title == "Test"
            mock_search.assert_called_once()

    async def test_search_timeout(self, provider):
        """Test search timeout handling."""
        query = SearchQuery(query="test", max_results=5)
        
        with patch.object(provider, '_execute_search', side_effect=TimeoutError()):
            with pytest.raises(ProviderTimeoutError):
                await provider.search(query)
```

### Test Data

- Use factories for test data generation
- Mock external API calls
- Test with realistic data sizes
- Include edge cases and error conditions

## Documentation

### Documentation Standards

1. **API Documentation**: Keep `api-reference.md` updated
2. **Configuration**: Update `../operators/configuration.md` for new settings
3. **Getting Started**: Update setup instructions as needed
4. **Code Comments**: Explain complex logic and algorithms
5. **Architecture Decisions**: Document in `docs/adrs/`

### Writing Documentation

- Use clear, concise language
- Include practical examples
- Test all code examples
- Add diagrams for complex concepts
- Keep formatting consistent

### Documentation Structure

```
├── README.md                 # Project overview and quick start
├── docs/users/getting-started.md      # Detailed setup guide
├── docs/operators/configuration.md   # Complete configuration reference
├── docs/developers/api-reference.md  # Tool and API documentation
├── docs/developers/contributing.md   # This file
├── docs/developers/development.md    # Development workflows
└── docs/
    ├── architecture/        # System design documentation
    ├── deployment/          # Deployment guides
    ├── troubleshooting/     # Problem-solving guides
    └── adrs/               # Architecture decision records
```

## Pull Request Process

### 1. Prepare Your Changes

```bash
# Ensure your branch is up to date
git checkout main
git pull upstream main
git checkout your-feature-branch
git rebase main

# Run tests and linting
uv run pytest
ruff check --fix .
ruff format .

# Commit your changes
git add .
git commit -m "feat(scope): description"
```

### 2. Create Pull Request

1. **Push to your fork**:
   ```bash
   git push origin your-feature-branch
   ```

2. **Open PR on GitHub** with:
   - Clear title and description
   - Reference to related issues
   - Summary of changes
   - Testing performed
   - Breaking changes (if any)

### 3. PR Template

```markdown
## Description
Brief description of what this PR does.

## Related Issues
Fixes #123

## Changes Made
- [ ] Added new provider integration
- [ ] Updated documentation
- [ ] Added tests

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing performed

## Breaking Changes
None / List any breaking changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Tests added/updated
```

### 4. Review Process

1. **Automated checks** must pass (CI/CD, tests, linting)
2. **Code review** by maintainers
3. **Address feedback** promptly
4. **Final approval** and merge

### 5. After Merge

```bash
# Clean up your local repository
git checkout main
git pull upstream main
git branch -d your-feature-branch
git push origin --delete your-feature-branch
```

## Community Guidelines

### Code of Conduct

We follow the [Contributor Covenant](https://www.contributor-covenant.org/):

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Respect different viewpoints
- Help maintain a positive environment

### Communication

- **GitHub Issues**: Bug reports and feature requests
- **Pull Requests**: Code discussions
- **Discussions**: General questions and ideas

### Getting Help

- Check existing issues and documentation
- Ask questions in GitHub Discussions
- Be specific about your problem
- Include relevant code and error messages

## Specific Contribution Areas

### Adding New Providers

To add a new search provider:

1. **Check if MCP server exists** for the provider
2. **Add provider configuration** to `provider_config.py`
3. **Create provider wrapper** inheriting from `GenericMCPProvider`
4. **Add comprehensive tests**
5. **Update documentation**

Example minimal provider implementation:

```python
# providers/newprovider_mcp.py
from .generic_mcp import GenericMCPProvider

class NewProviderMCPProvider(GenericMCPProvider):
    """New provider integration using embedded MCP server."""
    
    def __init__(self):
        super().__init__("newprovider")
    
    # Only override if special handling needed
    # Otherwise, GenericMCPProvider handles everything
```

### Improving Performance

Focus areas for performance contributions:

- **Caching optimizations**: Better cache keys and invalidation
- **Concurrent execution**: Parallel provider requests
- **Response times**: Optimize critical paths
- **Memory usage**: Efficient data structures
- **Provider selection**: Smarter routing algorithms

### Documentation Improvements

High-impact documentation areas:

- **Getting started guides**: User onboarding
- **Configuration examples**: Real-world setups
- **Troubleshooting guides**: Common problems
- **API examples**: Practical usage patterns
- **Architecture guides**: System understanding

Thank you for contributing to MCP Search Hub! Your contributions help make intelligent search more accessible and powerful for everyone.