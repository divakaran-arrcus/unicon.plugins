"""Manual test script for the ArcOS (arcos) unicon plugin against a real device.

Usage (from your pyATS venv):

    # Set environment variables
    export ARCOS_HOSTNAME=rtr1
    export ARCOS_IP=10.9.206.2
    export ARCOS_PORT=10001
    export ARCOS_USERNAME=root
    export ARCOS_PASSWORD=arrcus

    cd /Users/divakaran/arrcus_workspace/unicon.plugins
    source /Users/divakaran/arrcus_workspace/pyats_env/venv/bin/activate
    python src/unicon/plugins/tests/test_arcos_real.py

Make sure your editable install of this fork is active:

    pip install -e .

before running this script, so that the ArcOS plugin from this repo is used.
"""

from __future__ import annotations

import os
import sys

from unicon import Connection


def main() -> int:
    # Read connection details from environment variables
    hostname = os.getenv("ARCOS_HOSTNAME", "rtr1")
    ip = os.getenv("ARCOS_IP", "10.9.206.2")
    port = int(os.getenv("ARCOS_PORT", "10001"))
    username = os.getenv("ARCOS_USERNAME", "root")
    password = os.getenv("ARCOS_PASSWORD", "arrcus")

    conn = Connection(
        hostname=hostname,
        start=[f"ssh -p {port} {username}@{ip}"],
        os="arcos",
        platform="arcos",
        credentials={
            "default": {
                "username": username,
                "password": password,
            }
        },
        mit=True,
        log_buffer=True,
    )

    print(f"Connecting to {hostname} ({ip}:{port}) with os='arcos'...")
    conn.connect()
    print("Connected. Current state:", conn.state_machine.current_state)

    print("\n=== Executing 'show version' ===")
    output = conn.execute("show version")
    print(output)

    print("\n=== Executing 'show interface swp*' ===")
    output = conn.execute("show interface swp* | nomore")
    print(output)

    print("\n=== Testing configuration with commit ===")
    config_str = """
interface loopback11
 type    softwareLoopback
 enabled true
 subinterface 0
  ipv4 address 11.11.11.11
   prefix-length 32
  exit
  enabled true
 exit
 """
    conn.configure(config_str)

    print("\n=== Executing 'show interface loopback11' ===")
    output = conn.execute("show interface loopback11 | nomore")
    print(output)

    print("\nDisconnecting...")
    conn.disconnect()
    print("Disconnected.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
