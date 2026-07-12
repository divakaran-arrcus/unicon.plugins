"""Unit tests for the ArcOS Configure service commit-abort handling.

Drives the Configure service's commit logic with a *buffer-driven* mock spawn
that mimics real ``spawn.expect`` -- earliest-byte-position matching against a
simulated device buffer, with buffer consumption -- so the tests are faithful
to how pexpect actually behaves. In particular this reproduces the case the
sibling Load service warns about: an async ``Aborted:`` line (from a
config-triggered process restart) landing in the buffer BEFORE the real
``Commit complete``.

The config-send (GenericConfigure.call_service) is patched to a no-op so the
tests isolate the commit path.

Run with::

    cd unicon.plugins
    python -m pytest src/unicon/plugins/arcos/tests/test_arcos_configure_abort.py -v
"""

import re
import unittest
from unittest.mock import patch

from unicon.core.errors import SubCommandFailure
from unicon.plugins.generic.service_implementation import Configure as GenericConfigure

# Trailing config prompt arcOS returns to after commit completes / aborts.
PROMPT = "\nroot@rtr1(config)#"

# Real arcOS device commit responses (captured on the lab via confd_cli).
COMMIT_COMPLETE = "Commit complete." + PROMPT
NO_MODIFICATIONS = "% No modifications to commit" + PROMPT
COMMIT_ABORTED = ("Aborted: '': Deletion of front panel interface 'swp1' "
                  "is not allowed.") + PROMPT
COMMIT_FAILED = "Commit failed: some backend error" + PROMPT
# H1 / R1: an async 'Aborted:' from a config-triggered process restart lands in
# the byte stream BEFORE the real 'Commit complete' -- the commit SUCCEEDS.
ASYNC_ABORT_THEN_COMPLETE = ("Aborted: Subsystem 'isis' restarted\n"
                             "Commit complete." + PROMPT)


def _pat_str(p):
    return p if isinstance(p, str) else getattr(p, "pattern", str(p))


class BufferSpawn:
    """Mock spawn that mimics ``spawn.expect``: earliest-byte-position match of
    a pattern list against a simulated device buffer, consuming through the
    match (like pexpect). ``commit``/``yes`` load ``commit_output`` into the
    buffer. Non-commit expects (exec-prompt resync after abort/end) succeed.
    """

    def __init__(self, commit_output, timeout_first=False):
        self.commit_output = commit_output
        self.timeout_first = timeout_first  # first commit expect times out (Proceed?)
        self._commit_expects = 0
        self.sent = []
        self._last = None
        self.match_re = None
        self._buf = ""

    def sendline(self, s):
        self.sent.append(s)
        self._last = s
        if s in ("commit", "yes"):
            self._buf = self.commit_output

    def expect(self, patterns, timeout=None, *args, **kwargs):
        as_list = patterns if isinstance(patterns, (list, tuple)) else [patterns]
        pat_strs = [_pat_str(p) for p in as_list]
        # Commit / reject-confirm expects carry a success marker -> drive them
        # against the buffer. Everything else (exec-prompt resync) just succeeds.
        if not any("Commit complete" in ps for ps in pat_strs):
            self._buf = ""
            self.match_re = None
            return 0
        self._commit_expects += 1
        if self.timeout_first and self._commit_expects == 1:
            raise TimeoutError("Timeout: device blocking at Proceed? prompt")
        best_i, best_m = None, None
        for i, ps in enumerate(pat_strs):
            m = re.search(ps, self._buf, re.MULTILINE)
            if m and (best_m is None or m.start() < best_m.start()):
                best_i, best_m = i, m
        if best_i is None:
            raise TimeoutError("Timeout: no commit terminal string matched")
        self.match_re = best_m
        self._buf = self._buf[best_m.end():]  # consume through the match
        return best_i


def _make_service(spawn):
    from unicon.plugins.arcos.services.configure import Configure
    from unittest.mock import MagicMock

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
    with patch.object(GenericConfigure, "call_service", return_value=None):
        try:
            service.call_service(command=["no interface swp1"])
        except Exception as exc:  # noqa: BLE001 - test captures the outcome
            raised = exc
    return spawn, service, raised


class TestCommitAbortFastFail(unittest.TestCase):
    """A commit rejected with 'Aborted:' must fail FAST -- no 'yes' Proceed retry."""

    def test_does_not_send_yes(self):
        spawn, _, _ = _run(COMMIT_ABORTED)
        self.assertNotIn("yes", spawn.sent)

    def test_raises_subcommand_failure(self):
        _, _, raised = _run(COMMIT_ABORTED)
        self.assertIsInstance(raised, SubCommandFailure)

    def test_reason_preserves_device_message(self):
        # M1: the failure carries the real device reason (via match_re), not a
        # generic fallback.
        _, _, raised = _run(COMMIT_ABORTED)
        self.assertIn("front panel interface", str(raised))

    def test_sends_abort_and_recovers_to_enable(self):
        spawn, service, _ = _run(COMMIT_ABORTED)
        self.assertIn("abort", spawn.sent)
        service.connection.state_machine.update_cur_state.assert_called_with("enable")


class TestCommitFailedFastFail(unittest.TestCase):
    def test_does_not_send_yes(self):
        spawn, _, _ = _run(COMMIT_FAILED)
        self.assertNotIn("yes", spawn.sent)

    def test_raises_subcommand_failure(self):
        _, _, raised = _run(COMMIT_FAILED)
        self.assertIsInstance(raised, SubCommandFailure)


class TestAsyncAbortNoiseTreatedAsSuccess(unittest.TestCase):
    """H1 / R1: an async 'Aborted:' (process restart) that lands BEFORE the real
    'Commit complete' must NOT fail the commit -- it succeeded."""

    def test_commit_succeeds_despite_async_abort(self):
        _, _, raised = _run(ASYNC_ABORT_THEN_COMPLETE)
        self.assertIsNone(raised)

    def test_does_not_abort_the_candidate(self):
        spawn, _, _ = _run(ASYNC_ABORT_THEN_COMPLETE)
        self.assertNotIn("abort", spawn.sent)


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
    """The abort fix also touches the genuine-timeout -> 'yes' Proceed branch."""

    def test_proceed_prompt_commit_succeeds(self):
        spawn, service, raised = _run(COMMIT_COMPLETE, timeout_first=True)
        self.assertIsNone(raised)
        self.assertIn("yes", spawn.sent)
        self.assertNotIn("abort", spawn.sent)
        service.connection.state_machine.update_cur_state.assert_called_with("enable")

    def test_genuine_timeout_raises_via_yes_then_abort(self):
        spawn, _, raised = _run("")  # no terminal string ever appears
        self.assertIsInstance(raised, SubCommandFailure)
        self.assertIn("yes", spawn.sent)
        self.assertIn("abort", spawn.sent)


if __name__ == "__main__":
    unittest.main()
