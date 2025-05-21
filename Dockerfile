# Builder stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18.x (required by MCP servers)
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv (as specified in CLAUDE.md)
RUN pip install --no-cache-dir uv

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies using uv
RUN uv pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Install Node.js MCP servers globally
RUN npm install -g firecrawl-mcp-server @modelcontextprotocol/server-exa @ppl-ai/perplexity-mcp tavily-mcp@0.2.0

# Install Python MCP server
RUN uv pip install --no-cache-dir mcp-search-linkup

# Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV TRANSPORT=streamable-http

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18.x (required by MCP servers)
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages and code from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/lib/node_modules/ /usr/lib/node_modules/
COPY --from=builder /usr/bin/node /usr/bin/node
COPY --from=builder /usr/bin/npm /usr/bin/npm
COPY --from=builder /usr/bin/npx /usr/bin/npx

# Copy application code
COPY . .

# Set up a non-root user for security
RUN groupadd -r mcpuser && useradd -r -g mcpuser mcpuser
RUN chown -R mcpuser:mcpuser /app
USER mcpuser

# Create a directory for startup check files
RUN mkdir -p /app/healthchecks

# Expose the port
EXPOSE ${PORT}

# Define health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the application
CMD ["python", "-m", "mcp_search_hub.main", "--transport", "${TRANSPORT}", "--host", "0.0.0.0", "--port", "${PORT}"]