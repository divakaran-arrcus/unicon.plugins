"""State Machine for ArcOS connection plugin.

Defines the state machine with states and transitions for ArcOS devices.
"""

from unicon.statemachine import State, Path, StateMachine

from .patterns import ArcosPatterns
from .statements import ArcosStatements


patterns = ArcosPatterns()


class ArcosStateMachine(StateMachine):
    """State machine for ArcOS devices.

    Implements a hierarchical state machine with the following states:
    1. bash (Linux shell)
    2. enable (CLI exec mode)
    3. config (configuration mode)
    """

    def create(self):  # type: ignore[override]
        """Create the state machine states and paths."""

        # ==================
        # Define States
        # ==================

        # ArcOS prompts examples:
        #   bash:   root@hostname:~#
        #   exec:   root@hostname#
        #   config: root@hostname(config)#
        bash = State("bash", patterns.bash_prompt)
        # Create enable state; exec and enable are the same in ArcOS
        enable = State("enable", patterns.exec_prompt)
        exec_state = enable
        config = State("config", patterns.config_prompt)

        # ==================
        # Define Transitions
        # ==================

        # bash -> enable: use 'cli' command
        bash_to_exec = Path(bash, exec_state, "cli", None)

        # enable -> bash: use 'exit' command
        exec_to_bash = Path(exec_state, bash, "exit", None)

        # enable -> config: use 'config' command
        exec_to_config = Path(exec_state, config, "config", None)

        # config -> enable: use 'end' command
        config_to_exec = Path(config, exec_state, "end", None)

        # config -> bash: use 'end' then 'exit' (multi-step transition)
        config_to_bash = Path(config, bash, "end\rexit", None)

        # ==================
        # Add states and paths to the state machine
        # ==================

        self.add_state(bash)
        self.add_state(enable)
        self.add_state(config)

        self.add_path(bash_to_exec)
        self.add_path(exec_to_bash)
        self.add_path(exec_to_config)
        self.add_path(config_to_exec)
        self.add_path(config_to_bash)

        # Set default state (where connection starts)
        # ArcOS devices land in bash after SSH login
        self.add_default_statements(ArcosStatements.press_return_statement())
