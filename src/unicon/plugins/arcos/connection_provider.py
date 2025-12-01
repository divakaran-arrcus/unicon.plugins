"""Connection provider for ArcOS plugin.

Defines how the connection is established and managed.
"""

from unicon.plugins.generic import GenericSingleRpConnectionProvider
from unicon.eal.dialogs import Dialog

from .statements import ArcosStatements


class ArcosConnectionProvider(GenericSingleRpConnectionProvider):
    """Connection provider for ArcOS devices.

    Handles the connection establishment and initial state setup.
    """

    def get_connection_dialog(self):  # type: ignore[override]
        """Get the dialog for connection establishment.

        Reuse the generic connection dialog (which is credential-aware)
        and append ArcOS-specific statements.

        Returns:
            Dialog: Dialog with statements for handling connection prompts.
        """
        base_dialog = super().get_connection_dialog()
        arcos_dialog = Dialog(
            [
                ArcosStatements.confirm_statement(),
                ArcosStatements.press_return_statement(),
            ]
        )
        return base_dialog + arcos_dialog

    def establish_connection(self):  # type: ignore[override]
        """Establish connection to the device.

        This method handles the initial connection and transitions to exec mode.
        """
        # Call parent class method to handle basic connection
        super().establish_connection()

        # After connection, we should be in bash state (root@hostname:~#)
        # Transition to enable/exec state (root@hostname#) by running 'cli' command
        self.connection.state_machine.go_to(
            "enable",
            self.connection.spawn,
            context=self.connection.context,
            timeout=self.connection.settings.BASH_TO_EXEC_TIMEOUT,
        )
