#!/usr/bin/env python3
"""
Stop Continuous Position Monitor

Stops the running continuous position monitor service gracefully.
Sends SIGTERM to the monitor process.

Usage:
    python scripts/stop_continuous_monitor.py
"""

import os
import signal
import sys
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def find_monitor_process():
    """Find the running continuous monitor process."""
    try:
        # Use pgrep to find the process
        result = subprocess.run(
            ["pgrep", "-f", "continuous_position_monitor.py"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            return [int(pid) for pid in pids if pid]
        return []

    except Exception as e:
        print(f"Error finding monitor process: {e}")
        return []


def stop_monitor():
    """Stop the continuous monitor process."""
    print("=" * 70)
    print("STOPPING CONTINUOUS POSITION MONITOR")
    print("=" * 70)

    # Find monitor processes
    pids = find_monitor_process()

    if not pids:
        print("No continuous monitor process found")
        print("Either not running or already stopped")
        return True

    print(f"Found {len(pids)} monitor process(es): {pids}")

    # Send SIGTERM to each process
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"✓ Sent SIGTERM to process {pid}")
        except ProcessLookupError:
            print(f"⚠ Process {pid} not found (may have already stopped)")
        except Exception as e:
            print(f"✗ Error stopping process {pid}: {e}")

    print("\n" + "=" * 70)
    print("✓ CONTINUOUS POSITION MONITOR STOPPED")
    print("=" * 70)
    return True


def main():
    """Main entry point."""
    success = stop_monitor()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
