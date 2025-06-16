#!/usr/bin/env python3
"""
Claude Desktop Setup Script for MCP Search Hub

This script helps users quickly configure MCP Search Hub with Claude Desktop
by generating the appropriate configuration file and validating API keys.
"""

import json
import os
import platform
import sys
from pathlib import Path


def get_claude_config_path() -> Path:
    """Get the Claude Desktop configuration file path for the current platform."""
    system = platform.system().lower()

    if system == "darwin":  # macOS
        return (
            Path.home()
            / "Library/Application Support/Claude/claude_desktop_config.json"
        )
    if system == "windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA environment variable not found")
        return Path(appdata) / "Claude/config/claude_desktop_config.json"
    if system == "linux":
        return Path.home() / ".config/Claude/config/claude_desktop_config.json"
    raise RuntimeError(f"Unsupported platform: {system}")


def get_api_keys() -> dict[str, str]:
    """Interactively collect API keys from the user."""
    print("🔑 API Key Configuration")
    print("=" * 50)
    print("Enter your API keys (press Enter to skip a provider):")
    print()

    providers = {
        "TAVILY_API_KEY": {
            "name": "Tavily",
            "url": "https://tavily.com/",
            "description": "Web search and research",
            "required": True,
        },
        "EXA_API_KEY": {
            "name": "Exa",
            "url": "https://exa.ai/",
            "description": "Neural search and research",
            "required": True,
        },
        "LINKUP_API_KEY": {
            "name": "Linkup",
            "url": "https://linkup.ai/",
            "description": "Deep web search",
            "required": True,
        },
        "FIRECRAWL_API_KEY": {
            "name": "Firecrawl",
            "url": "https://firecrawl.dev/",
            "description": "Web scraping and crawling",
            "required": False,
        },
        "PERPLEXITY_API_KEY": {
            "name": "Perplexity",
            "url": "https://perplexity.ai/",
            "description": "AI-powered research",
            "required": False,
        },
    }

    api_keys = {}

    for key, info in providers.items():
        required_text = " (REQUIRED)" if info["required"] else " (optional)"
        print(f"🔹 {info['name']}{required_text}")
        print(f"   {info['description']}")
        print(f"   Get your API key at: {info['url']}")

        api_key = input(f"   Enter {info['name']} API key: ").strip()

        if api_key:
            api_keys[key] = api_key
            print(f"   ✅ {info['name']} API key saved")
        elif info["required"]:
            print(f"   ⚠️  {info['name']} is required for basic functionality")
        else:
            print(f"   ⏭️  Skipping {info['name']}")

        print()

    return api_keys


def create_config(api_keys: dict[str, str], advanced: bool = False) -> dict:
    """Create the Claude Desktop configuration."""

    # Base environment variables
    env_vars = {"LOG_LEVEL": "INFO"}

    # Add API keys
    env_vars.update(api_keys)

    # Add advanced configuration if requested
    if advanced:
        env_vars.update(
            {
                "TAVILY_TIMEOUT": "15000",
                "EXA_TIMEOUT": "20000",
                "LINKUP_TIMEOUT": "15000",
                "FIRECRAWL_TIMEOUT": "30000",
                "PERPLEXITY_TIMEOUT": "25000",
                "CACHE_TTL": "300",
                "DEFAULT_BUDGET": "0.10",
            }
        )

    # Detect Python path
    python_path = sys.executable

    return {
        "mcpServers": {
            "mcp-search-hub": {
                "command": python_path,
                "args": ["-m", "mcp_search_hub.main", "--transport", "stdio"],
                "env": env_vars,
            }
        }
    }


def validate_installation() -> bool:
    """Validate that MCP Search Hub is properly installed."""
    try:
        import mcp_search_hub  # noqa: F401

        print("✅ MCP Search Hub is installed and importable")
        return True
    except ImportError as e:
        print(f"❌ MCP Search Hub not found: {e}")
        print("Please install it first with: uv pip install -r requirements.txt")
        return False


def backup_existing_config(config_path: Path) -> Path | None:
    """Backup existing configuration file if it exists."""
    if config_path.exists():
        backup_path = config_path.with_suffix(".json.backup")
        import shutil

        shutil.copy2(config_path, backup_path)
        print(f"📋 Existing config backed up to: {backup_path}")
        return backup_path
    return None


def merge_with_existing_config(new_config: dict, config_path: Path) -> dict:
    """Merge new configuration with existing one."""
    if not config_path.exists():
        return new_config

    try:
        with open(config_path) as f:
            existing_config = json.load(f)

        # Merge mcpServers sections
        if "mcpServers" not in existing_config:
            existing_config["mcpServers"] = {}

        existing_config["mcpServers"].update(new_config["mcpServers"])

        print("🔄 Merged with existing configuration")
        return existing_config

    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  Could not read existing config: {e}")
        print("Creating new configuration file")
        return new_config


def main():
    """Main setup function."""
    print("🚀 MCP Search Hub - Claude Desktop Setup")
    print("=" * 50)
    print()

    # Validate installation
    if not validate_installation():
        sys.exit(1)

    # Get configuration path
    try:
        config_path = get_claude_config_path()
        print(f"📍 Claude Desktop config: {config_path}")
        print()
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    # Collect API keys
    api_keys = get_api_keys()

    if not api_keys:
        print("❌ No API keys provided. At least one provider is required.")
        sys.exit(1)

    # Ask about advanced configuration
    print("🔧 Configuration Options")
    print("=" * 30)
    advanced = (
        input("Include advanced configuration (timeouts, caching)? [y/N]: ").lower()
        == "y"
    )
    print()

    # Create configuration
    new_config = create_config(api_keys, advanced)

    # Ensure config directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing configuration
    backup_existing_config(config_path)

    # Merge with existing configuration
    final_config = merge_with_existing_config(new_config, config_path)

    # Write configuration
    try:
        with open(config_path, "w") as f:
            json.dump(final_config, f, indent=2)

        print("✅ Configuration saved successfully!")
        print(f"📁 Location: {config_path}")
        print()

        # Show summary
        print("📋 Configuration Summary")
        print("=" * 30)
        env_vars = final_config["mcpServers"]["mcp-search-hub"]["env"]

        enabled_providers = []
        for key, name in [
            ("TAVILY_API_KEY", "Tavily"),
            ("EXA_API_KEY", "Exa"),
            ("LINKUP_API_KEY", "Linkup"),
            ("FIRECRAWL_API_KEY", "Firecrawl"),
            ("PERPLEXITY_API_KEY", "Perplexity"),
        ]:
            if key in env_vars:
                enabled_providers.append(name)

        print(f"🔌 Enabled providers: {', '.join(enabled_providers)}")
        print(
            f"🐍 Python path: {final_config['mcpServers']['mcp-search-hub']['command']}"
        )
        print(f"📝 Log level: {env_vars.get('LOG_LEVEL', 'INFO')}")

        if advanced:
            print("⚙️  Advanced configuration enabled")

        print()
        print("🎉 Setup Complete!")
        print("=" * 20)
        print("1. Restart Claude Desktop completely")
        print("2. In a new conversation, ask: 'What MCP tools do you have available?'")
        print("3. Test with: 'Search for recent AI developments'")
        print()
        print("📚 For more help, see: docs/CLAUDE_DESKTOP_SETUP.md")

    except OSError as e:
        print(f"❌ Failed to write configuration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
