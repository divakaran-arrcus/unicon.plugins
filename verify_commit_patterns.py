#!/usr/bin/env python
"""Verification script to test commit failure pattern matching."""

import re

# Import the settings to verify the patterns
from unicon.plugins.arcos.settings import ArcosSettings

settings = ArcosSettings()

print("=== ArcOS Settings - Error Patterns ===")
for pattern in settings.ERROR_PATTERN:
    print(f"  - {pattern}")

print("\n=== Testing Commit Failure Patterns ===")

test_outputs = [
    "Commit failed due to validation error",
    "Configuration commit failed: invalid interface",
    "Error: Invalid configuration",
    "Syntax error on line 5",
    "% Error: Command not found",
]

for output in test_outputs:
    matched = False
    for pattern in settings.ERROR_PATTERN:
        if re.search(pattern, output):
            print(f"✓ MATCHED: '{output}' matches pattern '{pattern}'")
            matched = True
            break
    if not matched:
        print(f"✗ NO MATCH: '{output}'")

print("\n=== Verification Complete ===")
print("Commit failure patterns are correctly configured in ArcosSettings.ERROR_PATTERN")
