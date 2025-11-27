"""
Patterns for ArcOS connection plugin

Defines regex patterns for matching various prompts and outputs.
"""


class ArcosPatterns:
    """Regex patterns for ArcOS prompts and messages."""

    # Bash prompt: root@<hostname>:~# (has :~ before #)
    bash_prompt = r"^.*root@[^\s]+:~[#$]\s*$"

    # Exec mode prompt: root@<hostname># (no :~, no parentheses, no config)
    # This must NOT match config prompts or bash prompts
    exec_prompt = r"^.*root@[^\s:()]+#\s*$"

    # Config mode prompt: root@<hostname>(config)# or root@<hostname>(config-if)# etc.
    config_prompt = r"^.*root@[^\s]+\(config[^\)]*\)#\s*$"

    # Password prompts
    password_prompt = r"[Pp]assword:\s*$"

    # Username prompt
    username_prompt = r"[Uu]sername:\s*$|[Ll]ogin:\s*$"

    # Are you sure prompts
    confirm_prompt = r"\[confirm\]|\[yes/no\]"

    # Press return to continue
    press_return = r"Press RETURN to get started"

    # Connection refused
    connection_refused = r"Connection (refused|closed)"

    # Bad passwords
    bad_passwords = r"(Bad passwords|Access denied|Authentication failed)"

    # Commit messages
    commit_success = r"(Commit complete|Configuration committed successfully)"
    commit_failed = r"(Commit failed|Configuration commit failed)"

    # Error messages
    error_pattern = r"(% Error|% Invalid|Syntax error|syntax error)"
