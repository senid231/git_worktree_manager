from __future__ import annotations

SUPPORTED_SHELLS = ("bash", "zsh")

_SHELL_TEMPLATE = """\
# GWT shell integration
gwt_cd() {{
  local dir
  dir="$(command gwt cd "$@")" && cd "$dir"
}}
alias gcd='gwt_cd'
eval "$(gwt --show-completion {shell})"
"""


def generate_shell_init(shell: str) -> str:
    """Generate shell init snippet for the given shell."""
    if shell not in SUPPORTED_SHELLS:
        raise ValueError(f"Unsupported shell: {shell}. Supported: {', '.join(SUPPORTED_SHELLS)}")
    return _SHELL_TEMPLATE.format(shell=shell)
