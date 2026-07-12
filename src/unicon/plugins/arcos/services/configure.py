"""Configure service for ArcOS.

Implements configuration mode operations with automatic commit support.

The commit command is handled separately from config commands using raw
spawn.expect() to avoid GenericConfigure's dialog.process() loop, which
can false-match on spinner characters (\\b|, \\b/, \\b-, \\b\\) that arcOS
emits during long commits.  This is the same approach used by the Load
service.
"""

import logging

from unicon.plugins.generic.service_implementation import Configure as GenericConfigure
from unicon.eal.dialogs import Statement, Dialog
from unicon.core.errors import SubCommandFailure

from ..patterns import ArcosPatterns

log = logging.getLogger(__name__)
patterns = ArcosPatterns()

# How long to wait for the exec prompt after end/abort.
_SETTLE_TIMEOUT = 20


class Configure(GenericConfigure):
    """Configure service for ArcOS devices with automatic commit support.

    Extends the generic Configure service to add automatic commit functionality
    for ArcOS devices which use confd-style configuration.

    Config commands are sent through GenericConfigure normally.  The "commit"
    command is handled separately via raw spawn.expect() so that spinner
    characters do not cause false pattern matches or timeouts.
    """

    def call_service(self, command=None, reply=None, timeout=None,
                     commit=True, *args, **kwargs):  # type: ignore[override]
        """Configure the device with optional automatic commit.

        Args:
            command: Configuration command(s) to execute (str or list).
            reply: Optional dialog for handling interactive prompts.
            timeout: Command timeout in seconds.
            commit: Whether to auto-commit changes (default: True).
        """
        commit_timeout = timeout or self.connection.settings.COMMIT_TIMEOUT

        # Dialog to auto-answer unexpected commit prompts with "no" (defensive)
        commit_dialog = Dialog([
            Statement(
                pattern=r".*" + patterns.uncommitted_changes_prompt + r".*",
                action="sendline(no)",
                loop_continue=True,
                continue_timer=False,
            ),
        ])

        # Merge with existing reply dialog if provided
        if reply:
            commit_dialog += reply
        reply = commit_dialog

        # Build kwargs for parent call (exclude 'commit' as parent doesn't know it)
        parent_kwargs = kwargs.copy()
        parent_kwargs.pop("commit", None)

        if command is not None:
            parent_kwargs["command"] = command
        if reply is not None:
            parent_kwargs["reply"] = reply
        if timeout is not None:
            parent_kwargs["timeout"] = timeout

        if not commit or not command:
            # No commit needed — let parent handle everything normally
            return super().call_service(**parent_kwargs)

        # --- Commit path: send config commands, then handle commit ourselves ---

        # Keep device in config mode after parent finishes config commands
        # (GenericConfigure's call_service transitions to end_state at the end)
        original_end_state = self.end_state
        self.end_state = "config"
        try:
            super().call_service(**parent_kwargs)
        finally:
            self.end_state = original_end_state

        # Now handle commit with raw spawn.expect() (spinner-safe)
        spawn = self.get_handle()

        log.debug("ArcOS Configure: committing configuration")
        spawn.sendline("commit")

        _commit_done = False
        _commit_error = None

        # Recognize an explicit device rejection ("Aborted: ..." / "Commit
        # failed ...") alongside success. A rejected commit never produces a
        # success string, so matching it here lets us fail fast (~1s) via the
        # existing abort/recover path instead of waiting the full
        # COMMIT_TIMEOUT and then a needless "yes" Proceed retry.
        _commit_expect = [
            r"Commit complete",
            r"% No modifications to commit",
            patterns.commit_aborted,
            patterns.commit_failed,
        ]

        def _reject_reason():
            try:
                return str(spawn.match.match_output).strip().splitlines()[-1][:200]
            except Exception:
                return "commit aborted/failed"

        try:
            idx = spawn.expect(_commit_expect, timeout=commit_timeout)
            if idx in (2, 3):
                _commit_error = f"commit rejected by device: {_reject_reason()}"
            else:
                _commit_done = True
                if idx == 0:
                    log.debug("ArcOS Configure: commit complete")
                else:
                    log.debug("ArcOS Configure: no modifications to commit (no-op)")
        except Exception:
            # Genuine timeout — may be blocking at "Proceed? [yes,no]"
            log.info(
                "ArcOS Configure: commit timed out, sending 'yes' "
                "for possible Proceed prompt"
            )
            spawn.sendline("yes")
            try:
                idx = spawn.expect(_commit_expect, timeout=30)
                if idx in (2, 3):
                    _commit_error = f"commit rejected by device: {_reject_reason()}"
                else:
                    _commit_done = True
                    log.info("ArcOS Configure: commit complete (via Proceed prompt)")
            except Exception as exc:
                _commit_error = (
                    f"commit did not produce 'Commit complete': {exc}"
                )

        if _commit_error:
            # Abort and return to enable mode
            log.error("ArcOS Configure: commit failed — aborting")
            try:
                spawn.sendline("abort")
                spawn.expect(patterns.exec_prompt, timeout=_SETTLE_TIMEOUT)
            except Exception:
                pass
            self.connection.state_machine.update_cur_state("enable")
            raise SubCommandFailure(f"commit failed: {_commit_error}")

        # Transition to enable mode
        log.debug("ArcOS Configure: sending 'end' to return to exec mode")
        spawn.sendline("end")
        try:
            spawn.expect(patterns.exec_prompt, timeout=_SETTLE_TIMEOUT)
        except Exception:
            pass
        self.connection.state_machine.update_cur_state("enable")
