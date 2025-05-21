# Docker Configuration Guide

This document provides comprehensive information about the Docker configuration for MCP Search Hub, including multi-stage builds, environment setup, health checks, and deployment best practices.

## Docker Architecture

MCP Search Hub uses a multi-stage Docker build to optimize image size and improve security:

### 1. Builder Stage

The builder stage is responsible for:
- Installing all build dependencies (including development packages)
- Setting up Python and Node.js environments
- Installing all Python and Node.js dependencies
- Installing the MCP provider servers
- Building any necessary components

### 2. Runtime Stage

The runtime stage is optimized for production and includes:
- Minimal runtime dependencies
- Security hardening
- Non-root user configuration
- Health check implementation
- Only the necessary artifacts from the builder stage

This approach significantly reduces the final image size and improves security by excluding build tools and intermediate artifacts.

## Docker Compose Configurations

MCP Search Hub provides three Docker Compose configurations:

### 1. Default Configuration (`docker-compose.yml`)

The default configuration is suitable for general usage and includes:
- The MCP Search Hub service
- A Redis instance for caching
- Basic health checks
- Standard environment configuration

```bash
# Run with default configuration
docker-compose up -d
```

### 2. Development Configuration (`docker-compose.dev.yml`)

The development configuration is optimized for development workflows:
- Uses the builder stage for live code reloading
- Mounts local code for easy development
- Sets more verbose logging
- Configures shorter cache TTLs
- Disables certain production safeguards

```bash
# Run with development configuration
docker-compose -f docker-compose.dev.yml up -d
```

### 3. Production Configuration (`docker-compose.prod.yml`)

The production configuration is optimized for production deployments:
- Uses the runtime stage for smaller and more secure images
- Configures resource limits and reservations
- Enables Redis caching with longer TTLs
- Configures proper logging and rotation
- Enforces strict security settings
- Sets up proper restart policies

```bash
# Run with production configuration
docker-compose -f docker-compose.prod.yml up -d
```

## Environment Configuration

MCP Search Hub uses environment variables for configuration. Example environment files are provided:

- `.env.example`: Base example with all available options
- `.env.dev.example`: Development-specific settings
- `.env.prod.example`: Production-specific settings

To use these files:

1. Copy the appropriate example file:
   ```bash
   # For development
   cp .env.dev.example .env
   
   # For production
   cp .env.prod.example .env.prod
   ```

2. Edit the file to include your actual API keys and customize settings:
   ```bash
   # Edit the environment file
   vim .env  # or any editor of your choice
   ```

3. Make sure to keep your environment files secure and never commit them to version control.

### Critical Environment Variables

The following environment variables are required:

| Variable | Purpose | Required |
|----------|---------|----------|
| `FIRECRAWL_API_KEY` | Firecrawl API key | Yes |
| `EXA_API_KEY` | Exa API key | Yes |
| `PERPLEXITY_API_KEY` | Perplexity API key | Yes |
| `LINKUP_API_KEY` | Linkup API key | Yes |
| `TAVILY_API_KEY` | Tavily API key | Yes |

## Health Checks

MCP Search Hub includes comprehensive health checks to ensure service reliability:

### Docker Health Check

The Dockerfile includes a health check configuration:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
```

This health check:
- Runs every 30 seconds
- Has a 10-second timeout
- Allows 20 seconds for initial startup
- Retries 3 times before marking the container as unhealthy
- Uses the `/health` endpoint to determine service health

### Health Check Endpoint

The `/health` endpoint provides detailed health information:
- Overall system health status
- Individual provider health status
- Rate limiting information
- Budget status

You can manually check the health status:

```bash
curl http://localhost:8000/health
```

The response includes:
- `status`: Overall health status (HEALTHY, DEGRADED, UNHEALTHY)
- `healthy_providers`: Number of healthy providers
- `total_providers`: Total number of providers
- `providers`: Detailed status for each provider

## Deployment Best Practices

### Resource Allocation

For production environments, configure appropriate resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 1G
```

Adjust these values based on your workload and available resources.

### Security Considerations

1. **Use a non-root user**: The Dockerfile sets up a non-root user (`mcpuser`) for improved security.

2. **Protect sensitive environment variables**: Consider using Docker secrets or a secure environment variable management system.

3. **Enable authentication**: Set `MIDDLEWARE_AUTH_ENABLED=true` and configure `API_KEYS` in production.

4. **Rate limiting**: Keep `MIDDLEWARE_RATE_LIMIT_ENABLED=true` to protect against abuse.

### Logging Configuration

The production Docker Compose configuration includes JSON logging with rotation:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "20m"
    max-file: "5"
```

This prevents logs from consuming too much disk space.

### Redis Persistence

Redis is configured with persistence to survive container restarts:

```yaml
command: ["redis-server", "--appendonly", "yes", "--maxmemory", "500mb", "--maxmemory-policy", "allkeys-lru"]
```

The Redis data is stored in a Docker volume for persistence.

## Building Custom Images

To build a custom Docker image:

```bash
# Build using default Dockerfile
docker build -t mcp-search-hub:latest .

# Build only the runtime stage
docker build --target runtime -t mcp-search-hub:runtime .

# Build only the builder stage
docker build --target builder -t mcp-search-hub:builder .
```

## Troubleshooting

### Container Startup Issues

If the container fails to start:

1. Check the logs:
   ```bash
   docker-compose logs mcp-search-hub
   ```

2. Verify environment variables:
   ```bash
   docker-compose config
   ```

3. Check health status:
   ```bash
   docker inspect --format='{{json .State.Health}}' mcp-search-hub
   ```

### Provider Connection Issues

If providers fail to initialize:

1. Verify API keys are correctly set in the environment variables
2. Check network connectivity to provider services
3. Examine the logs for specific provider initialization errors

### Performance Issues

If you experience performance issues:

1. Increase resource limits in Docker Compose configuration
2. Enable Redis caching by setting `REDIS_CACHE_ENABLED=true`
3. Adjust cache TTLs based on your usage patterns
4. Consider disabling unused providers to reduce resource usage

## Advanced Configuration

### Custom Redis Configuration

To use an external Redis instance:

1. Update the `REDIS_URL` environment variable:
   ```
   REDIS_URL=redis://your-redis-host:6379
   ```

2. Remove the Redis service from the Docker Compose file if you're using an external Redis instance.

### Load Balancing

For high-availability deployments:

1. Deploy multiple MCP Search Hub instances
2. Use a load balancer (like Nginx, HAProxy, or a cloud load balancer)
3. Configure health checks on the load balancer to route traffic only to healthy instances

