"""
Statements for ArcOS connection plugin.

Defines dialog statements for handling interactive prompts.
"""

from unicon.eal.dialogs import Statement

from .patterns import ArcosPatterns


# Create pattern instance
patterns = ArcosPatterns()


def send_yes(spawn):
    """Send 'yes' for confirmation prompts."""
    spawn.sendline("yes")


def send_return(spawn):
    """Send return/enter key."""
    spawn.sendline()


class ArcosStatements:
    """Collection of common dialog statements for ArcOS."""

    @classmethod
    def confirm_statement(cls):
        """Statement for handling confirmation prompts."""
        return Statement(
            pattern=patterns.confirm_prompt,
            action=send_yes,
            args=None,
            loop_continue=True,
            continue_timer=False,
        )

    @classmethod
    def press_return_statement(cls):
        """Statement for 'press return to continue' prompts."""
        return Statement(
            pattern=patterns.press_return,
            action=send_return,
            args=None,
            loop_continue=True,
            continue_timer=False,
        )
