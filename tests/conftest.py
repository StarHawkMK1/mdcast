import pytest

OPT_IN = {"visual": "--run-visual", "word": "--run-word", "hangul": "--run-hangul"}


def pytest_addoption(parser):
    parser.addoption("--run-visual", action="store_true", help="run visual golden-image tests")
    parser.addoption("--run-word", action="store_true", help="run Microsoft Word parity tests (Windows + Word)")
    parser.addoption(
        "--run-hangul", action="store_true", help="run Hancom Office (Hangul) COM tests (Windows + Hangul)"
    )


def pytest_collection_modifyitems(config, items):
    for marker, option in OPT_IN.items():
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=f"{marker} test: pass {option}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
