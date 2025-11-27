"""ArcOS (arcos) Unicon plugin.

Provides a single-RP connection implementation for Arrcus ArcOS devices.

ArcOS devices expose a Linux bash shell by default and use a `cli` command
to enter the network CLI, with a confd-style configuration mode.
"""

from unicon.plugins.generic import ServiceList
from unicon.bases.routers.connection import BaseSingleRpConnection

from .statemachine import ArcosStateMachine
from .settings import ArcosSettings
from .connection_provider import ArcosConnectionProvider
from .services import Configure, Execute


class ArcosServiceList(ServiceList):
    """Service list for ArcOS devices."""

    def __init__(self):
        super().__init__()
        self.configure = Configure
        self.execute = Execute


class ArcosSingleRpConnection(BaseSingleRpConnection):
    """Single-RP connection class for ArcOS devices."""

    os = "arcos"
    platform = "arcos"
    chassis_type = "single_rp"
    state_machine_class = ArcosStateMachine
    connection_provider_class = ArcosConnectionProvider
    subcommand_list = ArcosServiceList
    settings = ArcosSettings()
