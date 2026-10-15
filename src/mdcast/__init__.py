"""mdcast — Markdown ↔ docx · hwpx · pdf, 템플릿 기반 변환기."""

import warnings

# panflute 2.3.1 has an invalid escape sequence in a docstring; Python reports it as a
# SyntaxWarning the first time it compiles the module (e.g. the first run after install).
# Compile-time warnings carry the file path as their module, hence the leading ".*".
warnings.filterwarnings("ignore", category=SyntaxWarning, module=r".*panflute")

__version__ = "0.1.0.dev0"
