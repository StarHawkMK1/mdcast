from click.testing import CliRunner

from mdcast.cli import main


def test_version_prints_name_and_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "mdcast" in result.output
    assert "0.1.0" in result.output
