import click

from mdcast import __version__


@click.group()
@click.version_option(
    __version__,
    prog_name="mdcast",
    message="%(prog)s 버전 %(version)s",
    help="버전 정보를 표시하고 종료합니다.",
)
@click.help_option(help="도움말을 표시하고 종료합니다.")
def main() -> None:
    """mdcast — Markdown ↔ docx · hwpx · pdf, 템플릿 기반 변환기."""
