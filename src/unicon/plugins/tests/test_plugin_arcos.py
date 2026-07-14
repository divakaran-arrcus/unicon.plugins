"""Unit tests for ArcOS (arcos) unicon plugin.

Uses mock_device_cli with tests/mock_data/arcos/arcos_mock_data.yaml to verify
basic connect and execute behavior.
"""

import os
import shutil
import yaml
import unittest

from unicon import Connection


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_MOCKDATA_PATH = os.path.join(BASE_DIR, "mock_data")

with open(
    os.path.join(LOCAL_MOCKDATA_PATH, "arcos", "arcos_mock_data.yaml"), "rb"
) as datafile:
    mock_data = yaml.safe_load(datafile.read())


SKIP_NO_MOCK = shutil.which("mock_device_cli") is None


@unittest.skipIf(SKIP_NO_MOCK, "mock_device_cli not found on PATH; skipping ArcOS plugin tests")
class TestArcosPluginConnect(unittest.TestCase):

    def test_connect_to_enable_prompt(self):
        hostname = "arcos-router"
        c = Connection(
            hostname=hostname,
            start=[
                "mock_device_cli --os arcos --state bash --hostname {hostname}".format(
                    hostname=hostname
                )
            ],
            os="arcos",
            platform="arcos",
            username="root",
            password="arrcus",
            init_exec_commands=[],
            init_config_commands=[],
        )
        c.connect()
        # After connection provider, we should be at the enable prompt
        self.assertIn("root@{hostname}#".format(hostname=hostname), c.spawn.match.match_output)
        c.disconnect()


@unittest.skipIf(SKIP_NO_MOCK, "mock_device_cli not found on PATH; skipping ArcOS plugin tests")
class TestArcosPluginExecute(unittest.TestCase):

    def test_execute_show_version(self):
        hostname = "arcos-router"
        c = Connection(
            hostname=hostname,
            start=[
                "mock_device_cli --os arcos --state bash --hostname {hostname}".format(
                    hostname=hostname
                )
            ],
            os="arcos",
            platform="arcos",
            username="root",
            password="arrcus",
            init_exec_commands=[],
            init_config_commands=[],
        )
        c.connect()
        cmd = "show version"
        expected_response = mock_data["enable"]["commands"][cmd].strip()
        ret = c.execute(cmd).replace("\r", "")
        self.assertIn(expected_response, ret)
        c.disconnect()


@unittest.skipIf(SKIP_NO_MOCK, "mock_device_cli not found on PATH; skipping ArcOS plugin tests")
class TestArcosPluginConfigure(unittest.TestCase):
    """Exercise the config-mode statemachine transition + configure service."""

    def _connect(self):
        hostname = "arcos-router"
        c = Connection(
            hostname=hostname,
            start=[
                "mock_device_cli --os arcos --state bash --hostname {hostname}".format(
                    hostname=hostname
                )
            ],
            os="arcos",
            platform="arcos",
            username="root",
            password="arrcus",
            init_exec_commands=[],
            init_config_commands=[],
        )
        c.connect()
        return c

    def test_configure_with_commit(self):
        c = self._connect()
        # Enters config, sends the command, auto-commits, returns to enable.
        c.configure("interface swp1")
        self.assertTrue(c.state_machine.current_state == "enable")
        c.disconnect()

    def test_configure_no_commit(self):
        c = self._connect()
        c.configure("interface swp1", commit=False)
        self.assertTrue(c.state_machine.current_state == "enable")
        c.disconnect()


if __name__ == "__main__":
    unittest.main()
