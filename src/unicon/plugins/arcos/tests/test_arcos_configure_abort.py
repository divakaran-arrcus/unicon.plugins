"""Unit tests for the ArcOS Configure service commit-abort handling.

Drives the Configure service's commit logic with a *buffer-driven* mock spawn
that mimics real ``spawn.expect`` pattern matching against a simulated device
response. This makes the tests faithful: whether the service fast-fails a
rejected commit depends on whether its commit ``expect`` recognises the
device's ``Aborted:`` / ``Commit failed`` line -- exactly the behaviour under
test -- not on a hard-coded side-effect.

The config-send (GenericConfigure.call_service) is patched to a no-op so the
tests isolate the commit path.

Run with::

    cd unicon.plugins
    python -m pytest src/unicon/plugins/arcos/tests/test_arcos_configure_abort.py -v
"""

import re
import unittest
from unittest.mock import MagicMock, patch

from unicon.core.errors import SubCommandFailure
from unicon.plugins.generic.service_implementation import Configure as GenericConfigure

# Real arcOS device commit responses (captured on the lab via confd_cli).
COMMIT_COMPLETE = "Commit complete."
NO_MODIFICATIONS = "% No modifications to commit"
COMMIT_ABORTED = "Aborted: '': Deletion of front panel interface 'swp1' is not allowed."
COMMIT_FAILED = "Commit failed: some backend error"


def _pat_str(p):
    return p if isinstance(p, str) else getattr(p, "pattern", str(p))


class BufferSpawn:
    """Mock spawn whose ``expect`` matches a list of regex patterns against a
    simulated device buffer, returning the first matching index or raising a
    timeout when nothing matches -- like the real spawn.

    ``commit_output`` is what the device emits in response to ``commit``/``yes``.
    Non-commit expects (e.g. the exec-prompt resync after abort/end) always
    succeed.
    """

    def __init__(self, commit_output, timeout_first=False):
        self.commit_output = commit_output
        self.timeout_first = timeout_first  # first commit expect times out (Proceed?)
        self._commit_expects = 0
        self.sent = []
        self._last = None
        self.match = MagicMock()

    def sendline(self, s):
        self.sent.append(s)
        self._last = s

    def expect(self, patterns, timeout=None, *args, **kwargs):
        as_list = patterns if isinstance(patterns, (list, tuple)) else [patterns]
        pat_strs = [_pat_str(p) for p in as_list]
        is_commit_expect = any("Commit complete" in ps for ps in pat_strs)
        if not is_commit_expect:
            # exec-prompt / resync expect -- always matches.
            self.match.match_output = ""
            return 0
        self._commit_expects += 1
        if self.timeout_first and self._commit_expects == 1:
            raise TimeoutError("Timeout: device blocking at Proceed? prompt")
        buf = self.commit_output if self._last in ("commit", "yes") else ""
        for i, ps in enumerate(pat_strs):
            if re.search(ps, buf):
                self.match.match_output = buf
                return i
        raise TimeoutError("Timeout: no commit terminal string matched")


def _make_service(spawn):
    from unicon.plugins.arcos.services.configure import Configure

    connection = MagicMock()
    connection.spawn = spawn
    connection.settings.COMMIT_TIMEOUT = 300

    service = Configure.__new__(Configure)
    service.connection = connection
    service.context = {}
    service.start_state = "config"
    service.end_state = "enable"
    service.get_handle = MagicMock(return_value=spawn)
    return service


def _run(commit_output, timeout_first=False):
    """Run configure(command=[...]) against a device that returns commit_output;
    return (spawn, service, raised_exception_or_None)."""
    spawn = BufferSpawn(commit_output, timeout_first=timeout_first)
    service = _make_service(spawn)
    raised = None
    # Isolate the commit path: no-op the config-send.
    with patch.object(GenericConfigure, "call_service", return_value=None):
        try:
            service.call_service(command=["no interface swp1"])
        except Exception as exc:  # noqa: BLE001 - test captures the outcome
            raised = exc
    return spawn, service, raised


# ---------------------------------------------------------------------------
# NEW behaviour under test (RED against current code)
# ---------------------------------------------------------------------------

class TestCommitAbortFastFail(unittest.TestCase):
    """A commit rejected with 'Aborted:' must fail FAST -- recognised at the
    commit expect -- not fall through to the 'yes' Proceed retry + full timeout.
    """

    def test_raises_subcommand_failure(self):
        _, _, raised = _run(COMMIT_ABORTED)
        self.assertIsInstance(raised, SubCommandFailure)

    def test_does_not_send_yes(self):
        # The 'yes' Proceed retry only makes sense on a genuine timeout. A
        # device that explicitly Aborted must be recognised immediately.
        spawn, _, _ = _run(COMMIT_ABORTED)
        self.assertNotIn("yes", spawn.sent)

    def test_sends_abort_and_recovers_to_enable(self):
        spawn, service, _ = _run(COMMIT_ABORTED)
        self.assertIn("abort", spawn.sent)
        service.connection.state_machine.update_cur_state.assert_called_with("enable")


class TestCommitFailedFastFail(unittest.TestCase):
    """A commit rejected with 'Commit failed' must also fail fast (no 'yes')."""

    def test_does_not_send_yes(self):
        spawn, _, _ = _run(COMMIT_FAILED)
        self.assertNotIn("yes", spawn.sent)

    def test_raises_subcommand_failure(self):
        _, _, raised = _run(COMMIT_FAILED)
        self.assertIsInstance(raised, SubCommandFailure)


# ---------------------------------------------------------------------------
# Regression guards for the unchanged success paths (GREEN on current code)
# ---------------------------------------------------------------------------

class TestCommitSuccessPathsUnchanged(unittest.TestCase):

    def test_normal_commit_succeeds(self):
        spawn, service, raised = _run(COMMIT_COMPLETE)
        self.assertIsNone(raised)
        self.assertNotIn("yes", spawn.sent)
        self.assertNotIn("abort", spawn.sent)
        self.assertIn("commit", spawn.sent)
        service.connection.state_machine.update_cur_state.assert_called_with("enable")

    def test_noop_commit_succeeds(self):
        _, _, raised = _run(NO_MODIFICATIONS)
        self.assertIsNone(raised)


class TestCommitTimeoutPaths(unittest.TestCase):
    """The abort fix also touches the genuine-timeout -> 'yes' Proceed branch;
    guard that it still behaves correctly."""

    def test_proceed_prompt_commit_succeeds(self):
        # Device blocks until 'yes' (Proceed?), then commits -> success via yes.
        spawn, service, raised = _run(COMMIT_COMPLETE, timeout_first=True)
        self.assertIsNone(raised)
        self.assertIn("yes", spawn.sent)
        self.assertNotIn("abort", spawn.sent)
        service.connection.state_machine.update_cur_state.assert_called_with("enable")

    def test_genuine_timeout_raises_via_yes_then_abort(self):
        # No terminal string ever appears -> genuine timeout: yes IS tried,
        # then abort + SubCommandFailure (contrast with the fast-fail abort).
        spawn, _, raised = _run("")
        self.assertIsInstance(raised, SubCommandFailure)
        self.assertIn("yes", spawn.sent)
        self.assertIn("abort", spawn.sent)


if __name__ == "__main__":
    unittest.main()
