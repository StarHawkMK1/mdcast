import pytest


def pytest_addoption(parser):
    parser.addoption("--run-visual", action="store_true", help="run visual golden-image tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-visual"):
        return
    skip = pytest.mark.skip(reason="visual test: pass --run-visual")
    for item in items:
        if "visual" in item.keywords:
            item.add_marker(skip)
