# STDIO Transport Implementation

This document describes the implementation of STDIO transport for the MCP Search Hub, which allows running the server directly as a subprocess with standard input/output communication.

## Overview

STDIO transport enables MCP clients to use the MCP Search Hub directly through standard input/output streams rather than a network connection. This is useful for:

- Command-line tools and scripts
- Direct integration with applications
- Local development and testing
- Environments where HTTP connectivity isn't available or desired

## Implementation Details

The STDIO transport implementation consists of the following components:

### 1. Configuration Support

- Added `transport` field to the `Settings` model in `models/config.py`
- Updated `config.py` to read the `TRANSPORT` environment variable
- Default value is "streamable-http" for backward compatibility

### 2. Command-Line Argument Handling

The `main.py` module now includes command-line argument parsing with argparse:

- `--transport`: Choose between "streamable-http" and "stdio"
- `--host` and `--port`: For HTTP transport configuration
- `--log-level`: Set logging level
- Provider API keys: `--linkup-api-key`, `--exa-api-key`, etc.

Arguments set via command line override environment variables and defaults.

### 3. Server Initialization

The server initialization logic in `main.py:main()` now:

- Parses command-line arguments
- Updates environment variables based on provided arguments
- Gets settings that incorporate all configuration sources
- Runs the server with the specified transport protocol

### 4. Graceful Shutdown

The shutdown handler has been enhanced to properly handle both transport types:

- Ensures all provider connections are closed
- Implements special handling for STDIO transport
- Properly cancels and awaits pending tasks
- Improves error handling during shutdown

## Usage Examples

### Running with STDIO Transport

#### Using environment variables

```bash
export TRANSPORT=stdio
python -m mcp_search_hub.main
```

#### Using command-line argument

```bash
python -m mcp_search_hub.main --transport stdio
```

### Client Connection

Clients can connect to the STDIO-based server:

```python
from fastmcp import Client

# Connect to MCP Search Hub via STDIO
async with Client("mcp_search_hub.main") as client:
    # Use client...
```

## Testing

A test script `test_stdio.py` is provided to validate STDIO transport functionality:

```bash
python test_stdio.py
```

This script connects to the MCP Search Hub via STDIO transport and performs test operations.

## Performance Considerations

- STDIO transport is generally faster for local usage as it avoids network overhead
- HTTP transport is required for remote connections and multi-client scenarios
- STDIO transport has lower latency but doesn't support concurrent requests from multiple clients
