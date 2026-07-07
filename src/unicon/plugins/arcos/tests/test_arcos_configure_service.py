"""Unit tests for the ArcOS Configure service's commit handling.

Tests the commit-result matching in Configure.call_service() in isolation
using a mocked spawn object and a stubbed-out GenericConfigure.call_service()
(so only the "commit" stage — the part after config commands are sent — is
exercised). All interaction with the device (sendline, expect) is verified
through mocks.

Run with::

    cd unicon.plugins
    python -m pytest src/unicon/plugins/arcos/tests/test_arcos_configure_service.py -v
"""

import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_spawn(expect_side_effects, match_text="Commit complete"):
    spawn = MagicMock()
    spawn.expect.side_effect = expect_side_effects
    spawn.match_re = MagicMock()
    spawn.match_re.group.return_value = match_text
    return spawn


def _make_service(spawn, commit_timeout=300):
    from unicon.plugins.arcos.services.configure import Configure

    connection = MagicMock()
    connection.spawn = spawn
    connection.settings.COMMIT_TIMEOUT = commit_timeout
    connection.state_machine.current_state = "config"

    service = Configure.__new__(Configure)
    service.connection = connection
    service.context = {}
    service.start_state = "config"
    service.end_state = "enable"
    service.get_handle = MagicMock(return_value=spawn)
    return service


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConfigureCommitAborted(unittest.TestCase):
    """confd rejects the commit outright with an "Aborted:" line.

    This must be recognized IMMEDIATELY (first spawn.expect() call, matching
    the newly-added patterns.commit_aborted pattern) and raise
    SubCommandFailure with the abort reason -- NOT time out after
    COMMIT_TIMEOUT waiting for "Commit complete".
    """

    ABORT_TEXT = "Aborted: Only locator-node-length = 16 is supported for usid"

    def _run(self):
        from unicon.core.errors import SubCommandFailure

        # idx=2 => the third pattern (patterns.commit_aborted) matched.
        spawn = _make_mock_spawn(
            expect_side_effects=[
                2,      # commit -> "Aborted: ..." matched immediately
                None,   # abort -> exec_prompt
            ],
            match_text=self.ABORT_TEXT,
        )
        service = _make_service(spawn)

        with patch.object(
            type(service).__mro__[1], "call_service", return_value=None
        ):
            with self.assertRaises(SubCommandFailure) as ctx:
                service.call_service("locator functional usid", commit=True)
        return spawn, service, ctx

    def test_raises_subcommand_failure_with_abort_reason(self):
        _, _, ctx = self._run()
        self.assertIn(self.ABORT_TEXT, str(ctx.exception))

    def test_fails_on_first_expect_call_not_after_timeout(self):
        """Exactly one commit-expect call before abort -- proves this is a
        fast, direct match and not something reached only after a timeout
        + retry cycle."""
        spawn, _, _ = self._run()
        # calls: [0] commit expect (matches idx=2 directly) [1] abort->exec_prompt
        self.assertEqual(spawn.expect.call_count, 2)
        first_call_kwargs = spawn.expect.call_args_list[0][1]
        # Confirm commit_aborted pattern was included in the very first wait.
        first_call_patterns = spawn.expect.call_args_list[0][0][0]
        self.assertEqual(len(first_call_patterns), 3)

    def test_sends_abort_not_end(self):
        spawn, _, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertIn("commit", calls)
        self.assertIn("abort", calls)
        self.assertNotIn("end", calls)

    def test_state_machine_updated_to_enable(self):
        _, service, _ = self._run()
        service.connection.state_machine.update_cur_state.assert_called_with("enable")

    def test_aborted_via_proceed_prompt_path_also_fails_fast(self):
        """Aborted: line can also arrive after the timeout->'yes' retry
        (e.g. commit-message true devices) -- must still raise with reason,
        not the generic timeout message."""
        from unicon.core.errors import SubCommandFailure

        spawn = _make_mock_spawn(
            expect_side_effects=[
                Exception("first wait timed out"),  # commit -> timeout
                2,      # yes -> "Aborted: ..." matched
                None,   # abort -> exec_prompt
            ],
            match_text=self.ABORT_TEXT,
        )
        service = _make_service(spawn)

        with patch.object(
            type(service).__mro__[1], "call_service", return_value=None
        ):
            with self.assertRaises(SubCommandFailure) as ctx:
                service.call_service("locator functional usid", commit=True)
        self.assertIn(self.ABORT_TEXT, str(ctx.exception))


class TestConfigureCommitCompleteUnaffected(unittest.TestCase):
    """Regression guard: normal "Commit complete" path is untouched."""

    def _run(self):
        spawn = _make_mock_spawn(
            expect_side_effects=[
                0,      # commit -> "Commit complete" matched
                None,   # end -> exec_prompt
            ],
        )
        service = _make_service(spawn)

        with patch.object(
            type(service).__mro__[1], "call_service", return_value=None
        ):
            service.call_service("interface swp1", commit=True)
        return spawn, service

    def test_sends_end_not_abort(self):
        spawn, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertIn("end", calls)
        self.assertNotIn("abort", calls)

    def test_state_machine_updated_to_enable(self):
        _, service = self._run()
        service.connection.state_machine.update_cur_state.assert_called_with("enable")


class TestConfigureCommitNoModificationsUnaffected(unittest.TestCase):
    """Regression guard: "% No modifications to commit" no-op path untouched."""

    def _run(self):
        spawn = _make_mock_spawn(
            expect_side_effects=[
                1,      # commit -> "% No modifications to commit" matched
                None,   # end -> exec_prompt
            ],
        )
        service = _make_service(spawn)

        with patch.object(
            type(service).__mro__[1], "call_service", return_value=None
        ):
            service.call_service("interface swp1", commit=True)
        return spawn, service

    def test_sends_end_not_abort(self):
        spawn, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertIn("end", calls)
        self.assertNotIn("abort", calls)


class TestConfigureCommitTimeoutUnaffected(unittest.TestCase):
    """Regression guard: real timeout (no Aborted:, no Commit complete)
    still goes through the existing 'yes' retry + generic timeout message,
    unchanged by this fix."""

    def _run(self):
        from unicon.core.errors import SubCommandFailure

        spawn = _make_mock_spawn(
            expect_side_effects=[
                Exception("timed out"),   # commit -> timeout
                Exception("timed out"),   # yes -> timeout again
                None,                      # abort -> exec_prompt
            ],
        )
        service = _make_service(spawn)

        with patch.object(
            type(service).__mro__[1], "call_service", return_value=None
        ):
            with self.assertRaises(SubCommandFailure) as ctx:
                service.call_service("interface swp1", commit=True)
        return spawn, service, ctx

    def test_raises_generic_timeout_message(self):
        _, _, ctx = self._run()
        self.assertIn("commit did not produce 'Commit complete'", str(ctx.exception))

    def test_sends_yes_then_abort(self):
        spawn, _, _ = self._run()
        calls = [c[0][0] for c in spawn.sendline.call_args_list]
        self.assertIn("yes", calls)
        self.assertIn("abort", calls)
        self.assertLess(calls.index("yes"), calls.index("abort"))


if __name__ == "__main__":
    unittest.main()
