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
        # failed ...") alongside success, so we can fail fast via the existing
        # abort/recover path instead of waiting the full COMMIT_TIMEOUT + a
        # needless "yes" Proceed retry.
        _commit_expect = [
            r"Commit complete",
            r"% No modifications to commit",
            patterns.commit_aborted,
            patterns.commit_failed,
        ]
        # A matched "Aborted:"/"Commit failed" is only a CANDIDATE reject: an
        # async "Aborted:" from a config-triggered process restart can land in
        # the byte stream BEFORE the real "Commit complete" (the arcOS Load
        # service documents the same hazard), and pexpect matches the earliest
        # position. Disambiguate by re-scanning: a genuine abort returns to the
        # config prompt with no success marker; async noise is followed by the
        # real success marker.
        _reject_confirm = [
            r"Commit complete",
            r"% No modifications to commit",
            patterns.config_prompt,
        ]

        def _reject_reason():
            # Mirror Load._match_text -- the matched text is on match_re/match.
            m = getattr(spawn, "match_re", None) or getattr(spawn, "match", None)
            try:
                if m is not None and hasattr(m, "group"):
                    return m.group(0).strip().splitlines()[-1][:200]
            except Exception:
                pass
            return "commit aborted/failed"

        def _resolve(index):
            """Map a commit-expect index to (done, error), disambiguating a
            candidate reject (index 2/3) from pre-commit async noise."""
            if index in (0, 1):
                return True, None
            reason = _reject_reason()
            try:
                j = spawn.expect(_reject_confirm, timeout=commit_timeout)
            except Exception:
                return False, f"commit rejected by device: {reason}"
            if j in (0, 1):
                # Real success marker followed the async "Aborted:" -> the
                # commit actually completed; the rejection was noise.
                return True, None
            return False, f"commit rejected by device: {reason}"

        try:
            idx = spawn.expect(_commit_expect, timeout=commit_timeout)
            _commit_done, _commit_error = _resolve(idx)
            if _commit_done:
                log.debug("ArcOS Configure: commit complete / no modifications")
        except Exception:
            # Genuine timeout — may be blocking at "Proceed? [yes,no]"
            log.info(
                "ArcOS Configure: commit timed out, sending 'yes' "
                "for possible Proceed prompt"
            )
            spawn.sendline("yes")
            try:
                idx = spawn.expect(_commit_expect, timeout=30)
                _commit_done, _commit_error = _resolve(idx)
                if _commit_done:
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
