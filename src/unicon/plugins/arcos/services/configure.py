"""Configure service for ArcOS.

Implements configuration mode operations with automatic commit support.
"""

from unicon.plugins.generic.service_implementation import Configure as GenericConfigure
from unicon.eal.dialogs import Statement, Dialog

from ..patterns import ArcosPatterns

patterns = ArcosPatterns()


class Configure(GenericConfigure):
    """Configure service for ArcOS devices with automatic commit support.

    Extends the generic Configure service to add automatic commit functionality
    for ArcOS devices which use confd-style configuration.
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
        # Add explicit commit command to configuration
        if commit and command:
            if isinstance(command, str):
                command = command + "\ncommit"
            elif isinstance(command, list):
                cmd_list = list(command)
                cmd_list.append("commit")
                command = cmd_list

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

        return super().call_service(**parent_kwargs)
