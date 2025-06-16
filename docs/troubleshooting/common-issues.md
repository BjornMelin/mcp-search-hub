# Common Issues and Solutions

This guide covers the most frequently encountered issues when using MCP Search Hub and their solutions.

## Installation and Setup Issues

### Python Version Compatibility

**Problem**: `ModuleNotFoundError` or `SyntaxError` during startup

**Symptoms**:
```bash
ModuleNotFoundError: No module named 'fastmcp'
# OR
SyntaxError: invalid syntax (async/await usage)
```

**Solutions**:
```bash
# Check Python version (must be 3.10+)
python --version

# If using wrong version, install correct Python
# Ubuntu/Debian
sudo apt install python3.10 python3.10-venv

# macOS with Homebrew
brew install python@3.10

# Create virtual environment with correct Python
python3.10 -m venv venv
source venv/bin/activate
```

### Dependency Installation Failures

**Problem**: `uv` or `pip` installation fails

**Symptoms**:
```bash
ERROR: Could not find a version that satisfies the requirement fastmcp
# OR
ERROR: Failed building wheel for some-package
```

**Solutions**:
```bash
# Install uv if not available
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clear pip cache and reinstall
pip cache purge
uv pip install --no-cache-dir -r requirements.txt

# For macOS with M1/M2 chips
export ARCHFLAGS="-arch arm64"
uv pip install -r requirements.txt

# Alternative: use pip directly
pip install -r requirements.txt
```

## Configuration Issues

### API Key Problems

**Problem**: "Invalid API key" or "Authentication failed" errors

**Symptoms**:
```json
{
  "error": "ProviderAuthenticationError",
  "message": "Invalid API key for provider 'exa'",
  "provider": "exa"
}
```

**Solutions**:
```bash
# 1. Verify API key format
echo $EXA_API_KEY  # Should not be empty

# 2. Check .env file syntax (no spaces around =)
# WRONG: EXA_API_KEY = your_key
# RIGHT: EXA_API_KEY=your_key

# 3. Test API key directly
curl -H "Authorization: Bearer $EXA_API_KEY" https://api.exa.ai/search

# 4. Regenerate API key from provider dashboard
# Most providers allow regenerating keys if issues persist
```

### Provider Not Found Errors

**Problem**: "Provider not enabled" or "Provider not found"

**Symptoms**:
```json
{
  "error": "ProviderNotFoundError",
  "message": "Provider 'linkup' is not enabled or configured"
}
```

**Solutions**:
```bash
# 1. Check provider enablement
echo $LINKUP_ENABLED  # Should be 'true'

# 2. Verify API key is set
echo $LINKUP_API_KEY  # Should not be empty

# 3. Check provider configuration
python -c "
from mcp_search_hub.providers.provider_config import PROVIDER_CONFIGS
print('linkup' in PROVIDER_CONFIGS)
"

# 4. Enable provider explicitly
export LINKUP_ENABLED=true
export LINKUP_API_KEY=your_key_here
```

### Port Already in Use

**Problem**: "Address already in use" when starting server

**Symptoms**:
```bash
OSError: [Errno 48] Address already in use
```

**Solutions**:
```bash
# 1. Find process using port 8000
lsof -i :8000
# OR on Windows
netstat -ano | findstr :8000

# 2. Kill the process
kill -9 <PID>

# 3. Use different port
export PORT=8080
python -m mcp_search_hub.main

# 4. Check if Docker container is running
docker ps | grep 8000
docker stop <container_name>
```

## Runtime Issues

### Timeout Errors

**Problem**: Frequent timeout errors from providers

**Symptoms**:
```json
{
  "error": "ProviderTimeoutError",
  "message": "Search operation timed out for provider 'exa' after 5 seconds",
  "provider": "exa",
  "timeout_ms": 5000
}
```

**Solutions**:
```bash
# 1. Increase provider timeouts
export EXA_TIMEOUT=15000        # 15 seconds
export PERPLEXITY_TIMEOUT=20000  # 20 seconds

# 2. Check network connectivity
curl -w "time_total: %{time_total}s\n" -o /dev/null -s "https://api.exa.ai"

# 3. Test with simpler queries first
curl -X POST http://localhost:8000/search/combined \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "max_results": 1}'

# 4. Enable single provider to isolate issue
export EXA_ENABLED=true
export LINKUP_ENABLED=false
export PERPLEXITY_ENABLED=false
```

### Memory Issues

**Problem**: High memory usage or out-of-memory errors

**Symptoms**:
```bash
MemoryError: Unable to allocate memory
# OR gradual memory increase over time
```

**Solutions**:
```bash
# 1. Reduce cache size
export CACHE_MAX_SIZE=500       # Reduce from default 1000
export CACHE_TTL=180           # Shorter TTL (3 minutes)

# 2. Disable Redis if not needed
export REDIS_CACHE_ENABLED=false

# 3. Monitor memory usage
# Linux
free -m
ps aux | grep mcp_search_hub

# macOS
top -pid $(pgrep -f mcp_search_hub)

# 4. Restart server periodically in production
# Add to crontab for nightly restart
0 2 * * * docker restart mcp-search-hub
```

### Rate Limiting Issues

**Problem**: Frequent rate limit errors

**Symptoms**:
```json
{
  "error": "ProviderRateLimitError",
  "message": "Rate limit exceeded for provider 'linkup'",
  "retry_after": 60
}
```

**Solutions**:
```bash
# 1. Reduce request frequency
export LINKUP_REQUESTS_PER_MINUTE=30  # Reduce from default
export LINKUP_COOLDOWN_PERIOD=10      # Longer cooldown

# 2. Enable caching to reduce API calls
export CACHE_TTL=600                  # 10 minutes
export REDIS_CACHE_ENABLED=true

# 3. Use cascade execution instead of parallel
# This uses fewer providers per query
export DEFAULT_EXECUTION_STRATEGY=cascade

# 4. Check your provider quotas
curl -H "Authorization: Bearer $LINKUP_API_KEY" \
  https://api.linkup.so/quota
```

## Integration Issues

### Claude Desktop Integration

**Problem**: MCP tools not showing up in Claude Desktop

**Symptoms**:
- Claude responds "I don't have access to search tools"
- Tools not listed in available tools

**Solutions**:
```bash
# 1. Verify Claude Desktop configuration
cat ~/.claude/claude_desktop_config.json
# Should contain mcp-search-hub entry

# 2. Check if server starts correctly
python -m mcp_search_hub.main --transport stdio
# Should not show errors

# 3. Restart Claude Desktop completely
# Quit and restart the application

# 4. Check logs (macOS)
tail -f ~/Library/Logs/Claude/claude.log

# 5. Test with minimal configuration
{
  "mcpServers": {
    "search": {
      "command": "python",
      "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
      "env": {
        "LINKUP_API_KEY": "your_key_only"
      }
    }
  }
}
```

### Docker Issues

**Problem**: Docker container fails to start or connect

**Symptoms**:
```bash
docker: Error response from daemon: container failed to start
# OR
curl: (7) Failed to connect to localhost port 8000
```

**Solutions**:
```bash
# 1. Check Docker logs
docker logs mcp-search-hub

# 2. Verify .env file exists and has API keys
ls -la .env
cat .env | grep API_KEY

# 3. Check port mapping
docker ps | grep mcp-search-hub
# Should show 0.0.0.0:8000->8000/tcp

# 4. Test health endpoint
docker exec mcp-search-hub curl http://localhost:8000/health

# 5. Rebuild container
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Performance Issues

### Slow Response Times

**Problem**: Search responses taking too long

**Symptoms**:
- Responses consistently > 5 seconds
- Timeouts on complex queries

**Solutions**:
```bash
# 1. Enable caching
export REDIS_CACHE_ENABLED=true
export CACHE_REDIS_TTL=3600

# 2. Reduce max_results for faster responses
# In search requests, use max_results=5 instead of 20

# 3. Use faster providers for simple queries
export LINKUP_WEIGHT=0.9  # Prioritize fast provider
export TAVILY_WEIGHT=0.5  # Deprioritize slower provider

# 4. Increase concurrent requests
export MAX_CONCURRENT_REQUESTS=15

# 5. Monitor provider response times
curl http://localhost:8000/metrics | grep response_time
```

### High CPU Usage

**Problem**: Server consuming too much CPU

**Symptoms**:
```bash
# High CPU usage in top/htop
```

**Solutions**:
```bash
# 1. Reduce logging verbosity
export LOG_LEVEL=WARNING
export MIDDLEWARE_LOGGING_INCLUDE_BODY=false

# 2. Disable expensive features
export CACHE_FINGERPRINT_ENABLED=false
export CIRCUIT_BREAKER_ENABLED=false

# 3. Profile the application
python -m cProfile -o profile.stats -m mcp_search_hub.main

# 4. Check for runaway processes
pstree -p $(pgrep -f mcp_search_hub)
```

## Network and Connectivity Issues

### DNS Resolution Problems

**Problem**: "Name resolution failed" errors

**Symptoms**:
```bash
gaierror: [Errno -2] Name or service not known
```

**Solutions**:
```bash
# 1. Test DNS resolution
nslookup api.exa.ai
dig api.linkup.so

# 2. Check /etc/resolv.conf (Linux)
cat /etc/resolv.conf

# 3. Use public DNS servers
# Add to /etc/resolv.conf
nameserver 8.8.8.8
nameserver 8.8.4.4

# 4. For Docker, check network settings
docker network ls
docker network inspect bridge
```

### SSL/TLS Certificate Issues

**Problem**: SSL certificate verification failures

**Symptoms**:
```bash
SSLError: certificate verify failed
```

**Solutions**:
```bash
# 1. Update certificates (Linux)
sudo apt update && sudo apt install ca-certificates

# 2. Update Python certificates (macOS)
/Applications/Python\ 3.10/Install\ Certificates.command

# 3. Check certificate validity
openssl s_client -connect api.exa.ai:443 </dev/null

# 4. Temporary bypass (not recommended for production)
export PYTHONHTTPSVERIFY=0
```

## Debugging Tools

### Enable Debug Logging

```bash
# Maximum verbosity
export LOG_LEVEL=DEBUG
export MIDDLEWARE_LOGGING_LOG_LEVEL=DEBUG

# Start server with debug output
python -m mcp_search_hub.main 2>&1 | tee debug.log
```

### Health Check Commands

```bash
# Basic health check
curl http://localhost:8000/health

# Detailed provider status
curl http://localhost:8000/providers

# System metrics
curl http://localhost:8000/metrics

# Test individual provider
curl -X POST http://localhost:8000/providers/linkup/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "max_results": 1}'
```

### Configuration Validation

```python
# Check configuration loading
python -c "
from mcp_search_hub.config.settings import get_settings
settings = get_settings()
print(f'Enabled providers: {[p for p, cfg in settings.providers.items() if cfg.enabled]}')
print(f'API keys set: {[p for p, cfg in settings.providers.items() if cfg.api_key]}')
"
```

## Getting Help

### Log Collection

When reporting issues, collect these logs:

```bash
# 1. Server logs with debug enabled
LOG_LEVEL=DEBUG python -m mcp_search_hub.main > debug.log 2>&1

# 2. Configuration dump
python -c "
from mcp_search_hub.config.settings import get_settings
import json
settings = get_settings()
print(json.dumps(settings.dict(), indent=2, default=str))
" > config.json

# 3. System information
python --version > system_info.txt
uv --version >> system_info.txt
docker --version >> system_info.txt
curl --version >> system_info.txt
```

### Minimal Reproduction

Create a minimal reproduction case:

```bash
# 1. Create minimal .env
echo "LINKUP_API_KEY=your_key" > .env.minimal

# 2. Test with single provider
LINKUP_ENABLED=true \
EXA_ENABLED=false \
PERPLEXITY_ENABLED=false \
TAVILY_ENABLED=false \
FIRECRAWL_ENABLED=false \
python -m mcp_search_hub.main

# 3. Simple test query
curl -X POST http://localhost:8000/search/combined \
  -H "Content-Type: application/json" \
  -d '{"query": "hello world", "max_results": 1}'
```

### Support Channels

- **GitHub Issues**: Bug reports and feature requests
- **Documentation**: Check API_REFERENCE.md and CONFIGURATION.md
- **Health Check**: Always run `/health` endpoint first

---

For issues not covered here, please create a GitHub issue with the debugging information collected above.