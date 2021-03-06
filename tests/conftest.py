# coding: utf-8
import os

import pytest

import nxdrive

from . import DocRemote

pytest_plugins = "tests.pytest_random"


def pytest_namespace():
    """
    This namespace is used to store global variables for
    tests. They can be accessed with `pytest.<variable_name>`
    e.g. `pytest.nuxeo_url`
    """

    nuxeo_url = os.getenv(
        "NXDRIVE_TEST_NUXEO_URL", "http://localhost:8080/nuxeo"
    ).split("#")[0]
    password = os.getenv("NXDRIVE_TEST_PASSWORD", "Administrator")
    user = os.getenv("NXDRIVE_TEST_USER", "Administrator")
    version = nxdrive.__version__

    root_remote = DocRemote(
        nuxeo_url,
        user,
        "nxdrive-test-administrator-device",
        version,
        password=password,
        base_folder="/",
        timeout=60,
    )

    return {
        "nuxeo_url": nuxeo_url,
        "user": user,
        "password": password,
        "root_remote": root_remote,
        "version": version,
    }


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtest_makereport():
    """
    Delete captured logs if the test is not in failure.
    It will help keeping the memory usage at a descent level.
    """

    # Execute the test
    outcome = yield

    # Get the report
    report = outcome.get_result()

    if report.passed:
        # Remove captured logs to free memory
        report.sections = []
        outcome.force_result(report)


@pytest.fixture(autouse=True)
def cleanup_attrs(request):
    """
    Delete any attribute added in the test.
    It will help keeping the memory usage at a descent level.
    """
    if not request.instance:
        yield
    else:
        attr_orig = set(request.instance.__dict__.keys())
        yield
        for attr in set(request.instance.__dict__.keys()) - attr_orig:
            if attr.startswith("engine_"):
                engine = getattr(request.instance, attr)
                if engine.remote:
                    engine.remote.client._session.close()
            delattr(request.instance, attr)
