#!/usr/bin/env python
"""Generate client SDKs for MCP Search Hub from the OpenAPI schema.

This script fetches the OpenAPI schema from a running MCP Search Hub server
and generates client SDKs for various programming languages using the OpenAPI
Generator CLI.

Prerequisites:
- Java must be installed
- OpenAPI Generator CLI must be installed
  (https://openapi-generator.tech/docs/installation/)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx


def download_openapi_schema(url: str, output_file: str) -> bool:
    """Download the OpenAPI schema from the server.

    Args:
        url: URL of the OpenAPI schema endpoint
        output_file: File to save the schema to

    Returns:
        True if successful, False otherwise
    """
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()

        # Save the schema to the output file
        with open(output_file, "w") as f:
            f.write(json.dumps(response.json(), indent=2))

        print(f"Downloaded OpenAPI schema to {output_file}")
        return True
    except Exception as e:
        print(f"Error downloading OpenAPI schema: {e}")
        return False


def generate_client_sdk(
    schema_file: str,
    output_dir: str,
    language: str,
    package_name: str = "mcp_search_hub_client",
) -> bool:
    """Generate a client SDK for the specified language.

    Args:
        schema_file: Path to the OpenAPI schema file
        output_dir: Directory to output the generated SDK
        language: Programming language for the SDK
        package_name: Package name for the SDK

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Build the command
        cmd = [
            "openapi-generator-cli",
            "generate",
            "-i",
            schema_file,
            "-g",
            language,
            "-o",
            os.path.join(output_dir, language),
            "--package-name",
            package_name,
        ]

        # Add language-specific options
        if language == "python":
            cmd.extend(["--additional-properties", "pythonVersion=3.11"])
        elif language == "typescript-fetch":
            cmd.extend(["--additional-properties", "typescriptThreePlus=true"])

        # Run the command
        print(f"Generating {language} client SDK...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            print(f"Error generating {language} client SDK:")
            print(result.stderr)
            return False

        print(
            f"Successfully generated {language} client SDK in {os.path.join(output_dir, language)}"
        )
        return True
    except Exception as e:
        print(f"Error generating {language} client SDK: {e}")
        return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate client SDKs for MCP Search Hub"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/openapi.json",
        help="URL of the OpenAPI schema (default: http://localhost:8000/openapi.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="./clients",
        help="Directory to output the generated SDKs (default: ./clients)",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["python", "typescript-fetch", "go", "java"],
        help="Languages to generate clients for (default: python typescript-fetch go java)",
    )

    args = parser.parse_args()

    # Create a temporary directory for the OpenAPI schema
    temp_dir = Path("./temp")
    os.makedirs(temp_dir, exist_ok=True)
    schema_file = temp_dir / "openapi.json"

    try:
        # Download the OpenAPI schema
        if not download_openapi_schema(args.url, schema_file):
            sys.exit(1)

        # Generate client SDKs for each language
        success = True
        for language in args.languages:
            if not generate_client_sdk(schema_file, args.output_dir, language):
                success = False

        if not success:
            sys.exit(1)
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
