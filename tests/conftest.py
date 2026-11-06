"""Options shared by every suite under tests/.

`--workers` is named after Playwright's own flag
(https://playwright.dev/docs/test-parallel) and means the same thing: run the
suite on N worker processes, files in parallel, the tests inside one file in
order on one worker. pytest has no such flag itself -- this hands N to
pytest-xdist with `--dist loadfile`, which is the same split. A file keeps its
module fixtures and the accounts it makes on one worker, so nothing is
created once per worker.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--workers",
        default=None,
        metavar="N",
        help="run on N worker processes, one file per worker at a time "
        "(pytest-xdist -n N --dist loadfile). 'auto' uses one per CPU.",
    )


def _parse_workers(value: str) -> int | str:
    if value == "auto":
        return value
    if value.isdigit() and int(value) >= 1:
        return int(value)
    raise pytest.UsageError(
        f"--workers must be a whole number of at least 1, or 'auto', got {value!r}"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config):
    # Runs before pytest-xdist reads -n. Workers re-run this hook with the
    # controller's options, and must not try to start workers of their own.
    value = config.getoption("--workers")
    if value is None or hasattr(config, "workerinput"):
        return
    workers = _parse_workers(value)
    if workers == 1:
        return
    config.option.numprocesses = workers
    if config.option.dist == "no":
        config.option.dist = "loadfile"
