"""Settings for ArcOS connection plugin.

Defines default settings and configurations for ArcOS connections.
"""

from unicon.plugins.generic.settings import GenericSettings


class ArcosSettings(GenericSettings):
    """Settings for ArcOS connections."""

    def __init__(self):
        super().__init__()

        # Connection settings
        self.CONNECTION_TIMEOUT = 60
        self.EXPECT_TIMEOUT = 30

        # Graceful disconnect
        self.GRACEFUL_DISCONNECT_WAIT_SEC = 0.2
        self.POST_DISCONNECT_WAIT_SEC = 0.1

        # Error patterns
        self.ERROR_PATTERN = [
            r"% ?Error",
            r"% ?Invalid",
            r"Syntax error",
            r"syntax error",
            r"Error:",
            r"Commit failed",
            r"Configuration commit failed",
        ]

        # Configure mode settings
        self.CONFIG_TIMEOUT = 30
        self.CONFIG_POST_WAIT = 0.5

        # Execute settings
        self.EXEC_TIMEOUT = 30

        # Commit settings
        self.COMMIT_TIMEOUT = 60

        # Transition settings
        self.BASH_TO_EXEC_COMMAND = "cli"
        self.BASH_TO_EXEC_TIMEOUT = 10

        # Config mode commands
        self.CONFIGURE_COMMAND = "config"
        self.CONFIGURE_TIMEOUT = 10
        self.CONFIG_EXIT_COMMAND = "end"

        # Commit commands
        self.COMMIT_COMMAND = "commit"
        self.ABORT_COMMAND = "abort"

        # Prompt patterns (can be overridden)
        self.BASH_PROMPT = r"^.*root@[^\s]+[#$]\s*$"
        self.EXEC_PROMPT = r"^.*[^@\s]+#\s*$"
        self.CONFIG_PROMPT = r"^.*\(config[^\)]*\)#\s*$"

        # Enable/disable features
        self.IGNORE_CHATTY_TERM_OUTPUT = True
        self.TERM = "vt100"

        # HA settings (single RP for ArcOS)
        self.HA_INIT_EXEC_COMMANDS = []
        self.HA_INIT_CONFIG_COMMANDS = []
