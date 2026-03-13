"""Load service for ArcOS.

Implements ``device.load(remote_path)`` which runs:

  1. ``load override <remote_path>``  — from config mode, waits through the
     spinner until the "X KiB parsed in Y sec" success line or an "Error:"
     failure line.
  2. ``commit``                        — waits for "Commit complete." (direct),
     "Proceed? [yes,no]" (answers "yes" then waits), or "Aborted:".
  3. ``end``                           — returns to exec (enable) mode.

If any stage fails the service sends ``abort`` (returning to exec mode) and
raises ``SubCommandFailure``.

Spinner chars (\\, |, /, -) with backspace sequences appear before terminal
lines; they pass through ``spawn.expect()`` naturally without matching any of
our terminal patterns, so no special spinner handling is required.
"""

import logging

from unicon.bases.routers.services import BaseService
from unicon.core.errors import SubCommandFailure

from ..patterns import ArcosPatterns

log = logging.getLogger(__name__)

# How long (seconds) to wait for load and commit stages.
# Both operations can take up to ~2 minutes on large configs.
_DEFAULT_TIMEOUT = 120

# How long to wait for the prompt to settle after a success message.
_SETTLE_TIMEOUT = 20


class Load(BaseService):
    """ArcOS ``load override`` + ``commit`` service.

    After a successful commit the service sends ``end`` and returns the device
    to exec (enable) mode so subsequent API calls work without a state-machine
    transition.

    Usage::

        device.load('/tmp/my_config.cfg')
        device.load('/tmp/my_config.cfg', timeout=150)
    """

    def __init__(self, connection, context, **kwargs):
        super().__init__(connection, context, **kwargs)
        # The generic BaseService pre_service() transitions to start_state.
        # We start in config mode; the framework handles the transition for us.
        self.start_state = "config"
        # After call_service we will be in enable (exec) mode.
        self.end_state = "enable"
        self.timeout = _DEFAULT_TIMEOUT

    # ------------------------------------------------------------------
    # Main service implementation
    # ------------------------------------------------------------------

    def call_service(self, remote_path, timeout=_DEFAULT_TIMEOUT):
        """Run load override + commit on the device.

        Args:
            remote_path (str): Absolute path to the config file on the device
                (e.g. ``'/tmp/router.cfg'``).
            timeout (int): Maximum seconds to wait for each of the two long
                stages (load and commit).  Defaults to 120.

        Raises:
            SubCommandFailure: If ``load override`` reports an error, or if
                ``commit`` is aborted.  In both cases the device is left in
                exec mode via ``abort``.
        """
        spawn = self.get_handle()
        p = ArcosPatterns()

        # ── Stage 1: load override ─────────────────────────────────────────
        log.info("ArcOS Load: load override %s", remote_path)
        spawn.sendline(f"load override {remote_path}")

        # Spinner lines pass through; we wait for the terminal line:
        #   success → "20.98 KiB parsed in 13.94 sec (1.50 KiB/sec)"
        #   failure → "Error: failed to open file: ..."
        idx = spawn.expect(
            [
                r"\d+\.\d+ \S+iB parsed in \d+\.\d+ sec",
                r"Error:[^\r\n]+",
            ],
            timeout=timeout,
        )

        if idx == 1:
            error_text = self._match_text(spawn)
            self._drain_to_config_prompt(spawn, p)
            raise SubCommandFailure(
                f"load override '{remote_path}' failed: {error_text.strip()}"
            )

        log.info("ArcOS Load: load override succeeded")
        # Wait for the config prompt to ensure load output is fully consumed,
        # then drain any async messages (process restarts emit "Aborted:" or
        # "Subsystem stopped:" lines that must not bleed into commit).
        self._drain_to_config_prompt(spawn, p)
        self._drain_all_pending(spawn, p)

        # ── Stage 2: commit ────────────────────────────────────────────────
        log.info("ArcOS Load: committing")
        spawn.sendline("commit")

        # Match ONLY "Commit complete".  Do NOT include "Aborted:" or
        # "Proceed? [yes,no]" as patterns.
        #
        # The raw pexpect buffer can contain async "Aborted:" messages
        # from process restarts triggered by the config load, as well as
        # "Proceed? [yes,no]" on devices with ``commit-message true``.
        # Both appear BEFORE "Commit complete" in the byte stream
        # (overwritten on screen by \r + spinner chars).  pexpect matches
        # the earliest position, so including them as patterns causes
        # false matches.  By matching only "Commit complete", pexpect
        # scans past all such noise and finds the real success marker.
        #
        # For truly blocking Proceed? devices, "Commit complete" never
        # appears and we time out; the timeout handler sends "yes".
        # For real commit aborts, the config prompt appears without
        # "Commit complete"; we time out and report the failure.
        _commit_done = False
        _commit_error = None

        try:
            spawn.expect(r"Commit complete", timeout=timeout)
            _commit_done = True
            log.info("ArcOS Load: commit complete")
        except Exception:
            # Timeout — either blocking Proceed? or commit abort/no-mod.
            # Try sending "yes" in case device is blocking at Proceed?.
            log.info(
                "ArcOS Load: commit did not complete, sending 'yes' "
                "in case of Proceed prompt"
            )
            spawn.sendline("yes")
            try:
                spawn.expect(r"Commit complete", timeout=30)
                _commit_done = True
                log.info(
                    "ArcOS Load: commit complete (via proceed prompt)"
                )
            except Exception as exc:
                _commit_error = (
                    f"commit did not produce 'Commit complete': {exc}"
                )

        if _commit_error:
            self._abort(spawn, p)
            raise SubCommandFailure(
                f"commit failed: {_commit_error.strip()}"
            )

        self._drain_all_pending(spawn, p)

        # ── Stage 4: return to exec mode ──────────────────────────────────
        log.info("ArcOS Load: sending 'end' to return to exec mode")
        spawn.sendline("end")
        try:
            spawn.expect(p.exec_prompt, timeout=_SETTLE_TIMEOUT)
        except Exception:
            pass  # prompt may already be buffered

        # update_cur_state() is the correct API — current_state is read-only.
        self.connection.state_machine.update_cur_state("enable")
        log.info("ArcOS Load: load_config complete — now in exec mode")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_text(spawn):
        """Return the text of the most recent spawn.expect() match."""
        match = getattr(spawn, "match_re", None) or getattr(spawn, "match", None)
        if match is None:
            return "unknown error"
        if hasattr(match, "group"):
            return match.group(0)
        return str(match)

    @staticmethod
    def _drain_to_config_prompt(spawn, p, timeout=_SETTLE_TIMEOUT):
        """Consume spawn output until the config prompt appears.

        Uses a pattern without ``^``/``$`` anchors so it works regardless of
        what precedes the prompt in the pexpect buffer.
        """
        try:
            spawn.expect(r"root@[^\s()]+\(config\S*\)#", timeout=timeout)
        except Exception:
            pass  # prompt may already be in the buffer

    @staticmethod
    def _drain_all_pending(spawn, p, settle=2.0, max_drains=5):
        """Aggressively drain all pending output until the buffer is quiet.

        After a ``load override``, arcOS may emit asynchronous messages
        (process restarts, subsystem stops) that include words like
        "Aborted:" before the commit completes.  This method reads the
        buffer repeatedly until no new output arrives for ``settle`` seconds.
        """
        for _ in range(max_drains):
            try:
                spawn.expect(r".+", timeout=settle)
            except Exception:
                # No output for settle seconds — buffer is quiet
                break

    def _abort(self, spawn, p):
        """Send 'abort' to exit config mode after a commit failure.

        Leaves the device at the exec prompt and updates the state machine.
        """
        log.info("ArcOS Load: sending 'abort' after commit failure")
        try:
            spawn.sendline("abort")
            spawn.expect(p.exec_prompt, timeout=_SETTLE_TIMEOUT)
        except Exception as exc:
            log.warning("ArcOS Load: abort returned unexpected output: %s", exc)
        finally:
            # Always update state machine — we are in exec mode after abort.
            self.connection.state_machine.update_cur_state("enable")
