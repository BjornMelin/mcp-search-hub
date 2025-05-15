#!/usr/bin/env python
"""
Test script for MCP Search Hub STDIO transport mode.
This script creates a FastMCP client that connects to the MCP Search Hub server
using Python STDIO transport.
"""

import asyncio
from fastmcp import Client

async def main():
    """Run test with STDIO transport."""
    # Connect to MCP Search Hub via STDIO
    print("Connecting to MCP Search Hub via STDIO transport...")
    
    # Use the module path with stdio transport
    async with Client("mcp_search_hub.main") as client:
        # Get available tools
        tools = await client.list_tools()
        print(f"Available tools: {tools}")
        
        # If tools are available, try using the search tool
        if "search" in tools:
            print("\nTrying search tool...")
            response = await client.call_tool("search", {
                "query": "Latest developments in artificial intelligence",
                "max_results": 3
            })
            
            # Print the response
            print("\nSearch results:")
            print(f"Query: {response.query}")
            print(f"Providers used: {response.providers_used}")
            print(f"Total results: {response.total_results}")
            print(f"Total cost: ${response.total_cost:.6f}")
            print(f"Timing: {response.timing_ms:.2f}ms")
            
            # Print individual results
            print("\nTop results:")
            for i, result in enumerate(response.results[:3], 1):
                print(f"\n{i}. {result.title}")
                print(f"   URL: {result.url}")
                print(f"   Source: {result.source}")
                print(f"   Snippet: {result.snippet[:150]}...")
        
        else:
            print("Search tool not available")

if __name__ == "__main__":
    asyncio.run(main())