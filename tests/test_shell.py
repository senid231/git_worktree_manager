from __future__ import annotations

from gwt.shell import generate_shell_init


class TestGenerateShellInit:
    def test_bash_output(self) -> None:
        output = generate_shell_init("bash")
        assert "gwt_cd()" in output
        assert "alias gcd=" in output
        assert "--show-completion bash" in output

    def test_zsh_output(self) -> None:
        output = generate_shell_init("zsh")
        assert "gwt_cd()" in output
        assert "alias gcd=" in output
        assert "--show-completion zsh" in output

    def test_unsupported_shell_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="fish"):
            generate_shell_init("fish")
