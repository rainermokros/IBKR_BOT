#!/usr/bin/env python3
"""
Dashboard Startup Script

Launches the Streamlit dashboard for the V6 trading system.
Supports command-line arguments for port and debug mode.

Usage:
    python scripts/run_dashboard.py
    python scripts/run_dashboard.py --port 8502
    python scripts/run_dashboard.py --debug
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Launch V6 Trading System Dashboard"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port for Streamlit server (default: 8501)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (verbose logging)"
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (for production)"
    )

    return parser.parse_args()


def main():
    """Main entry point for dashboard startup."""
    # Parse arguments
    args = parse_args()

    # Get project root (assumes script is in scripts/ directory)
    project_root = Path(__file__).parent.parent
    app_path = project_root / "src" / "v6" / "system_monitor" / "dashboard" / "app.py"

    # Check if app.py exists
    if not app_path.exists():
        print(f"Error: Dashboard app not found at {app_path}")
        sys.exit(1)

    # Build Streamlit command
    # Set PYTHONPATH as environment variable for the subprocess
    cmd = [
        f"PYTHONPATH={project_root}",
        "streamlit",
        "run",
        str(app_path),
        "--server.port", str(args.port),
        "--server.headless", "true",  # Always run headless for production
    ]

    # Add project root to PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root) + ":" + env.get("PYTHONPATH", "")

    # Add headless mode if specified
    if args.headless:
        cmd.extend(["--server.headless", "true"])

    # Add debug mode if specified
    if args.debug:
        cmd.extend(["--logger.level", "debug"])

    # Print startup message
    print("=" * 60)
    print("V6 Trading System Dashboard")
    print("=" * 60)
    print(f"Port: {args.port}")
    print(f"Debug: {args.debug}")
    print(f"Headless: {args.headless}")
    print("=" * 60)
    print(f"Starting dashboard at http://localhost:{args.port}")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    try:
        # Launch Streamlit with PYTHONPATH set (use shell for env var expansion)
        subprocess.run(" ".join(cmd), check=True, shell=True, env=env)
    except KeyboardInterrupt:
        print("\nDashboard stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error starting dashboard: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
