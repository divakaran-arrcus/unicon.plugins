"""Execute service for ArcOS.

Implements command execution in exec mode with prompt stripping.
"""

import re

from unicon.plugins.generic.service_implementation import Execute as GenericExecute


class Execute(GenericExecute):
    """Execute service for ArcOS devices.

    Extends generic Execute service to strip the trailing prompt from output,
    which is necessary for clean JSON parsing and comparison.
    """

    def post_service(self, *args, **kwargs):  # type: ignore[override]
        """Post-process the output to strip the trailing prompt.

        This is called after the generic execute finishes, allowing us to
        clean up the output before returning it.
        """
        # Call parent's post_service first
        result = super().post_service(*args, **kwargs)

        # The result is a string with command output; strip trailing ArcOS prompt
        if isinstance(result, str):
            # Remove trailing prompt with optional newlines before it
            # ArcOS prompts like root@hostname# or root@hostname:~#
            result = re.sub(r"[\r\n]*root@[^\r\n]*$", "", result)
            result = result.strip()

        return result
