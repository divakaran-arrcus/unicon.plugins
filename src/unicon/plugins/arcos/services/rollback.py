"""Rollback service for ArcOS.

Implements ``device.rollback(sno=0)`` which runs:

  1. ``rollback configuration <sno>``  — from config mode, stages the rollback
     to the candidate config (fast, no spinner).
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

# How long (seconds) to wait for commit.
# Rollback commits can take up to ~2 minutes on large configs.
_DEFAULT_TIMEOUT = 120

# How long to wait for the prompt to settle after a success message.
_SETTLE_TIMEOUT = 20


class Rollback(BaseService):
    """ArcOS ``rollback configuration`` + ``commit`` service.

    After a successful commit the service sends ``end`` and returns the device
    to exec (enable) mode so subsequent API calls work without a state-machine
    transition.

    Usage::

        device.rollback()                    # rollback most recent commit
        device.rollback(sno=0)               # same as above
        device.rollback(sno=3, timeout=180)  # rollback to commit #3
    """

    def __init__(self, connection, context, **kwargs):
        super().__init__(connection, context, **kwargs)
        self.start_state = "config"
        self.end_state = "enable"
        self.timeout = _DEFAULT_TIMEOUT

    # ------------------------------------------------------------------
    # Main service implementation
    # ------------------------------------------------------------------

    def call_service(self, sno=0, timeout=_DEFAULT_TIMEOUT):
        """Run rollback configuration + commit on the device.

        Args:
            sno (int): Rollback sequence number.  0 = most recent commit
                (i.e. undo the last change).  Defaults to 0.
            timeout (int): Maximum seconds to wait for the commit stage.
                Defaults to 120.

        Raises:
            SubCommandFailure: If ``rollback configuration`` reports an error,
                or if ``commit`` is aborted.  In both cases the device is left
                in exec mode via ``abort``.
        """
        spawn = self.get_handle()
        p = ArcosPatterns()

        # ── Stage 1: rollback configuration <sno> ────────────────────────
        log.debug("ArcOS Rollback: rollback configuration %s", sno)
        spawn.sendline(f"rollback configuration {sno}")

        # Rollback stages to candidate config quickly — just wait for
        # the config prompt to confirm the command was accepted.
        self._drain_to_config_prompt(spawn, p)

        # ── Stage 2: commit ──────────────────────────────────────────────
        log.debug("ArcOS Rollback: committing")
        spawn.sendline("commit")

        _commit_done = False
        _commit_error = None

        try:
            spawn.expect(r"Commit complete", timeout=timeout)
            _commit_done = True
            log.debug("ArcOS Rollback: commit complete")
        except Exception:
            # Timeout — either blocking Proceed? or commit abort/no-mod.
            # Try sending "yes" in case device is blocking at Proceed?.
            log.info(
                "ArcOS Rollback: commit did not complete, sending 'yes' "
                "in case of Proceed prompt"
            )
            spawn.sendline("yes")
            try:
                spawn.expect(r"Commit complete", timeout=30)
                _commit_done = True
                log.info(
                    "ArcOS Rollback: commit complete (via proceed prompt)"
                )
            except Exception as exc:
                _commit_error = (
                    f"commit did not produce 'Commit complete': {exc}"
                )

        if _commit_error:
            self._abort(spawn, p)
            raise SubCommandFailure(
                f"rollback commit failed: {_commit_error.strip()}"
            )

        self._drain_all_pending(spawn, p)

        # ── Stage 3: return to exec mode ─────────────────────────────────
        log.debug("ArcOS Rollback: sending 'end' to return to exec mode")
        spawn.sendline("end")
        try:
            spawn.expect(p.exec_prompt, timeout=_SETTLE_TIMEOUT)
        except Exception:
            pass  # prompt may already be buffered

        # update_cur_state() is the correct API — current_state is read-only.
        self.connection.state_machine.update_cur_state("enable")
        log.debug("ArcOS Rollback: rollback complete — now in exec mode")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _drain_to_config_prompt(spawn, p, timeout=_SETTLE_TIMEOUT):
        """Consume spawn output until the config prompt appears."""
        try:
            spawn.expect(r"root@[^\s()]+\(config\S*\)#", timeout=timeout)
        except Exception:
            pass  # prompt may already be in the buffer

    @staticmethod
    def _drain_all_pending(spawn, p, settle=2.0, max_drains=5):
        """Drain all pending output until the buffer is quiet."""
        for _ in range(max_drains):
            try:
                spawn.expect(r".+", timeout=settle)
            except Exception:
                break

    def _abort(self, spawn, p):
        """Send 'abort' to exit config mode after a commit failure."""
        log.info("ArcOS Rollback: sending 'abort' after commit failure")
        try:
            spawn.sendline("abort")
            spawn.expect(p.exec_prompt, timeout=_SETTLE_TIMEOUT)
        except Exception as exc:
            log.warning("ArcOS Rollback: abort returned unexpected output: %s", exc)
        finally:
            self.connection.state_machine.update_cur_state("enable")
