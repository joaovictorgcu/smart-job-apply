"""The command a new reader runs first.

`python scripts/demo_server.py --fresh` is the front door: the README offers it
before anything else, and it is what `frontend/playwright.config.ts` launches.
Nothing exercised it. 1049 tests passed while two consecutive `--fresh` runs
left the second one dead on `WinError 32`, because the previous demo's headless
Chromium had not finished letting go of its profile — a bug found by running the
thing, which is precisely the gap these tests close.

So this file boots the real script as a subprocess, twice, with a browser opened
in between. It asserts what a person would notice: the API answers, the demo
account signs in, the offline provider is the one configured, and doing it all
again immediately still works.

Marked `e2e` and excluded from the default run: it spawns a server and launches
Chromium. `make e2e` runs it.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_SCRIPT = PROJECT_ROOT / "scripts" / "demo_server.py"

# The credentials the script prints, and the README repeats.
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-123"

BOOT_TIMEOUT_SECONDS = 90.0
POLL_SECONDS = 0.5


def free_port() -> int:
    """A port nobody is on, so the test never collides with a running dev server."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class DemoServer:
    """The script under test, as a subprocess, with its output kept for failures."""

    def __init__(self, data_dir: Path, log: Path) -> None:
        self.port = free_port()
        self.data_dir = data_dir
        self.log = log
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api"

    def start(self) -> None:
        handle = self.log.open("ab")
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(DEMO_SCRIPT),
                "--fresh",
                "--port",
                str(self.port),
                "--data-dir",
                str(self.data_dir),
            ],
            cwd=str(PROJECT_ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

    def wait_until_healthy(self) -> None:
        """Poll until the API answers, or say why it never will.

        The process is checked on every pass, not only at the end: a script that
        died on startup should fail this test with its own traceback rather than
        with ninety seconds of silence and a connection error.
        """
        assert self.process is not None
        deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            exit_code = self.process.poll()
            if exit_code is not None:
                pytest.fail(
                    f"demo_server.py exited with {exit_code} before serving:\n{self.output()}"
                )
            try:
                response = httpx.get(f"{self.base_url}/health", timeout=2.0)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(POLL_SECONDS)
        pytest.fail(f"demo_server.py never became healthy:\n{self.output()}")

    def output(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace")[-4000:]

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


@pytest.fixture
def demo(tmp_path: Path) -> Iterator[DemoServer]:
    server = DemoServer(tmp_path / "demo", tmp_path / "demo.log")
    try:
        yield server
    finally:
        server.stop()


def sign_in(server: DemoServer) -> str:
    response = httpx.post(
        f"{server.base_url}/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=30.0,
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


class TestTheFrontDoor:
    def test_it_boots_and_the_demo_account_signs_in(self, demo: DemoServer) -> None:
        demo.start()
        demo.wait_until_healthy()

        token = sign_in(demo)
        headers = {"Authorization": f"Bearer {token}"}
        status = httpx.get(f"{demo.base_url}/ai/status", headers=headers, timeout=30.0)

        assert status.status_code == 200, status.text
        body = status.json()
        # The demo must answer without a key and without the network: anything
        # else here means it would ask a new reader to sign up for something.
        assert body["configured"] is True
        assert body["provider"] == "stub"

    def test_a_second_fresh_run_survives_the_first_one_s_browser(
        self, demo: DemoServer, tmp_path: Path
    ) -> None:
        """The regression. On Windows the first demo's headless Chromium still
        holds `browser_profiles/user_1/.../leveldb/000003.log` for a moment
        after the server exits, and `--fresh` used to die trying to unlink it —
        so the second run never started at all."""
        demo.start()
        demo.wait_until_healthy()
        token = sign_in(demo)

        opened = httpx.post(
            f"{demo.base_url}/automation/session/start",
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
        assert opened.status_code == 200, opened.text
        assert opened.json()["browser_open"] is True

        # No graceful browser shutdown on purpose: this is the crash-and-restart
        # case, which is the one that failed.
        demo.stop()

        second = DemoServer(demo.data_dir, tmp_path / "demo-second.log")
        second.port = demo.port
        try:
            second.start()
            second.wait_until_healthy()

            assert sign_in(second)
        finally:
            second.stop()
