"""Unit tests for the ArcOS Load service.

Tests the Load service in isolation using a mocked spawn object.
All interaction with the device (sendline, expect) is verified through mocks.

Run with::

    cd unicon.plugins
    python -m pytest src/unicon/plugins/arcos/tests/test_arcos_load_service.py -v
"""

import unittest
from unittest.mock import MagicMock

# _DRAIN_STOP is what _drain_all_pending()'s expect() raises to signal "no more
# output".  We use Exception() so the drain loop breaks immediately.
_DRAIN_STOP = Exception("no more output")

# _COMMIT_TIMEOUT simulates the commit expect timing out (device blocking at
# Proceed? prompt — "Commit complete" never appears without sending "yes").
_COMMIT_TIMEOUT = Exception("commit timeout — device blocking at Proceed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_spawn(expect_side_effects):
    spawn = MagicMock()
    spawn.expect.side_effect = expect_side_effects
    spawn.match_re = MagicMock()
    spawn.match_re.group.return_value = "Aborted: '' test error"
    return spawn


def _make_service(spawn, current_state="config"):
    from unicon.plugins.arcos.services.load import Load

    connection = MagicMock()
    connection.spawn = spawn
    connection.state_machine.current_state = current_state

    service = Load.__new__(Load)
    service.connection = connection
    service.context = {}
    service.start_state = "config"
    service.end_state = "enable"
    service.timeout = 120
    service.get_handle = MagicMock(return_value=spawn)
    return service


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadServiceSuccess(unittest.TestCase):
    """Happy-path: load succeeds, commit matches "Commit complete" directly.

    expect() call sequence:
     [0] load override            → idx 0 (KiB parsed)
     [1] _drain_to_config_prompt  → None
     [2] _drain_all_pending[0]    → _DRAIN_STOP
     [3] commit: "Commit complete"→ None (single-pattern match)
     [4] _drain_all_pending[0]    → _DRAIN_STOP
     [5] end → exec_prompt        → None
    """

    def _run(self, timeout=120):
        spawn = _make_mock_spawn([
            0,             # load → success
            None,          # drain_to_config_prompt
            _DRAIN_STOP,   # drain_all_pending → quiet
            None,          # commit → "Commit complete" matched
            _DRAIN_STOP,   # drain after commit
            None,          # end → exec prompt
        ])
        service = _make_service(spawn)
        service.call_service("/tmp/test.cfg", timeout=timeout)
        return spawn, service

    def test_sendline_sequence(self):
        spawn, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertEqual(calls, [
            "load override /tmp/test.cfg",
            "commit",
            "end",
        ])

    def test_no_yes_sent(self):
        spawn, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertNotIn("yes", calls)

    def test_state_machine_updated_to_enable(self):
        _, service = self._run()
        service.connection.state_machine.update_cur_state.assert_called_with("enable")

    def test_custom_timeout_forwarded(self):
        spawn, _ = self._run(timeout=150)
        first_kwargs = spawn.expect.call_args_list[0][1]
        self.assertEqual(first_kwargs.get("timeout"), 150)


class TestLoadServiceSuccessViaYes(unittest.TestCase):
    """Commit times out (blocking Proceed?), 'yes' sent, then matches."""

    def _run(self):
        spawn = _make_mock_spawn([
            0,                 # load → success
            None,              # drain_to_config_prompt
            _DRAIN_STOP,       # drain_all_pending
            _COMMIT_TIMEOUT,   # commit → timeout
            None,              # yes → "Commit complete" matched
            _DRAIN_STOP,       # drain after commit
            None,              # end → exec prompt
        ])
        service = _make_service(spawn)
        service.call_service("/tmp/test.cfg")
        return spawn, service

    def test_sendline_sequence(self):
        spawn, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertEqual(calls, [
            "load override /tmp/test.cfg",
            "commit",
            "yes",
            "end",
        ])

    def test_state_machine_updated_to_enable(self):
        _, service = self._run()
        service.connection.state_machine.update_cur_state.assert_called_with("enable")


class TestLoadServiceLoadFailure(unittest.TestCase):
    """load override returns an Error line."""

    def test_raises_subcommand_failure(self):
        from unicon.core.errors import SubCommandFailure

        spawn = _make_mock_spawn([1, _DRAIN_STOP])
        spawn.match_re.group.return_value = "Error: No such file"
        service = _make_service(spawn)

        with self.assertRaises(SubCommandFailure) as ctx:
            service.call_service("/tmp/missing.cfg")
        self.assertIn("load override", str(ctx.exception))

    def test_does_not_send_commit(self):
        from unicon.core.errors import SubCommandFailure

        spawn = _make_mock_spawn([1, _DRAIN_STOP])
        service = _make_service(spawn)

        with self.assertRaises(SubCommandFailure):
            service.call_service("/tmp/missing.cfg")

        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertNotIn("commit", calls)


class TestLoadServiceCommitTimeout(unittest.TestCase):
    """Commit times out both initially and after 'yes' — total failure."""

    def _run(self):
        from unicon.core.errors import SubCommandFailure

        spawn = _make_mock_spawn([
            0,                 # load → success
            None,              # drain_to_config_prompt
            _DRAIN_STOP,       # drain_all_pending
            _COMMIT_TIMEOUT,   # commit → timeout
            _COMMIT_TIMEOUT,   # yes → timeout again
            None,              # abort → exec prompt
        ])
        service = _make_service(spawn)

        with self.assertRaises(SubCommandFailure) as ctx:
            service.call_service("/tmp/test.cfg")
        return spawn, service, ctx

    def test_raises_subcommand_failure(self):
        _, _, ctx = self._run()
        self.assertIn("commit", str(ctx.exception).lower())

    def test_sends_abort(self):
        spawn, _, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertIn("abort", calls)

    def test_sends_yes_before_abort(self):
        spawn, _, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertIn("yes", calls)
        self.assertLess(calls.index("yes"), calls.index("abort"))

    def test_does_not_send_end(self):
        spawn, _, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertNotIn("end", calls)

    def test_state_machine_updated_to_enable(self):
        _, service, _ = self._run()
        service.connection.state_machine.update_cur_state.assert_called_with("enable")


class TestLoadServiceTimeoutPassthrough(unittest.TestCase):
    """Timeout parameter is forwarded to long-running expects."""

    def test_load_stage_uses_custom_timeout(self):
        spawn = _make_mock_spawn([
            0, None, _DRAIN_STOP, None, _DRAIN_STOP, None,
        ])
        service = _make_service(spawn)
        service.call_service("/tmp/test.cfg", timeout=180)
        self.assertEqual(spawn.expect.call_args_list[0][1]["timeout"], 180)

    def test_commit_stage_uses_custom_timeout(self):
        spawn = _make_mock_spawn([
            0, None, _DRAIN_STOP, None, _DRAIN_STOP, None,
        ])
        service = _make_service(spawn)
        service.call_service("/tmp/test.cfg", timeout=180)
        # Fourth expect call is the commit
        self.assertEqual(spawn.expect.call_args_list[3][1]["timeout"], 180)


if __name__ == "__main__":
    unittest.main()
