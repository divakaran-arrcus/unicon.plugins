"""Manual test script for the ArcOS (arcos) unicon plugin against a real device.

Usage (from your pyATS venv):

    cd /Users/divakaran/arrcus_workspace/unicon.plugins
    source /Users/divakaran/arrcus_workspace/pyats_env/venv/bin/activate
    python test_arcos_real.py

This uses the following connection details (from testbed_test.yaml):

- os: arcos
- platform: arcos
- ip: 10.9.206.2
- port: 10001
- username: root
- password: arrcus

Make sure your editable install of this fork is active:

    pip install -e .

before running this script, so that the ArcOS plugin from this repo is used.
"""

from __future__ import annotations

import sys

from unicon import Connection


HOSTNAME = "rtr1"
IP = "10.9.206.2"
PORT = 10001
USERNAME = "root"
PASSWORD = "arrcus"


def main() -> int:
    conn = Connection(
        hostname=HOSTNAME,
        start=[f"ssh -p {PORT} {USERNAME}@{IP}"],
        os="arcos",
        platform="arcos",
        credentials={
            "default": {
                "username": USERNAME,
                "password": PASSWORD,
            }
        },
        mit=True,
        log_buffer=True,
    )

    print(f"Connecting to {HOSTNAME} ({IP}:{PORT}) with os='arcos'...")
    conn.connect()
    print("Connected. Current state:", conn.state_machine.current_state)

    print("\n=== Executing 'show version' ===")
    output = conn.execute("show version")
    print(output)

    print("\nDisconnecting...")
    conn.disconnect()
    print("Disconnected.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
