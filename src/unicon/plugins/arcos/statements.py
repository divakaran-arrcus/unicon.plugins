"""
Statements for ArcOS connection plugin.

Defines dialog statements for handling interactive prompts.
"""

from unicon.eal.dialogs import Statement

from .patterns import ArcosPatterns


# Create pattern instance
patterns = ArcosPatterns()


def send_password(spawn, password):
    """Send password when prompted."""
    spawn.sendline(password)


def send_username(spawn, username):
    """Send username when prompted."""
    spawn.sendline(username)


def send_yes(spawn):
    """Send 'yes' for confirmation prompts."""
    spawn.sendline("yes")


def send_return(spawn):
    """Send return/enter key."""
    spawn.sendline()


class ArcosStatements:
    """Collection of common dialog statements for ArcOS."""

    @classmethod
    def username_statement(cls, context):
        """Statement for handling username prompts."""
        return Statement(
            pattern=patterns.username_prompt,
            action=lambda spawn: send_username(
                spawn, context.get("username", context.get("default_username", "root"))
            ),
            args=None,
            loop_continue=True,
            continue_timer=False,
        )

    @classmethod
    def password_statement(cls, context):
        """Statement for handling password prompts."""
        return Statement(
            pattern=patterns.password_prompt,
            action=lambda spawn: send_password(
                spawn, context.get("password", context.get("default_password", ""))
            ),
            args=None,
            loop_continue=True,
            continue_timer=False,
        )

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
