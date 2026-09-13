"""`--fresh` must survive the browser it is racing.

The demo leaves a headless Chromium behind for a moment after its server exits,
and on Windows a file that process still holds cannot be unlinked. A plain
`rmtree` loses that race and kills the next demo with `WinError 32` before a
line of the app has run — which is exactly how it failed in practice: two
consecutive `--fresh` runs, the second one dead on
`browser_profiles/user_1/Default/Local Storage/leveldb/000003.log`.

So the rule is: retry briefly, keep the leftovers, and only refuse when what
survived is the database itself.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import demo_server  # noqa: E402


class TestWipe:
    def test_a_directory_that_deletes_cleanly_leaves_nothing(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "demo"
        (data_dir / "browser_profiles" / "user_1").mkdir(parents=True)
        (data_dir / "demo.db").write_bytes(b"x")

        assert demo_server.wipe(data_dir) == []
        assert not data_dir.exists()

    def test_a_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        assert demo_server.wipe(tmp_path / "never-existed") == []

    def test_a_locked_file_is_retried_and_then_survived(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Windows-only in the wild, so the lock is simulated: what is asserted
        is the policy — try more than once, then report rather than raise."""
        data_dir = tmp_path / "demo"
        data_dir.mkdir()
        locked = data_dir / "leveldb" / "000003.log"
        locked.parent.mkdir()
        locked.write_bytes(b"held open")
        calls: list[int] = []

        def _always_locked(path: Any, onexc: Any = None, **_kwargs: Any) -> None:
            calls.append(1)
            if onexc is not None:
                onexc(None, str(locked), PermissionError(32, "in use"))

        monkeypatch.setattr(demo_server.shutil, "rmtree", _always_locked)
        monkeypatch.setattr(demo_server.time, "sleep", lambda _seconds: None)

        survivors = demo_server.wipe(data_dir, attempts=3)

        assert survivors == [locked]
        assert len(calls) == 3

    def test_a_file_that_frees_itself_between_attempts_is_deleted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The real case: the browser lets go a few hundred milliseconds later."""
        data_dir = tmp_path / "demo"
        data_dir.mkdir()
        attempts: list[int] = []

        def _locked_once(path: Any, onexc: Any = None, **_kwargs: Any) -> None:
            attempts.append(1)
            if len(attempts) == 1 and onexc is not None:
                onexc(None, str(data_dir / "leveldb" / "000003.log"), PermissionError(32, "busy"))

        monkeypatch.setattr(demo_server.shutil, "rmtree", _locked_once)
        monkeypatch.setattr(demo_server.time, "sleep", lambda _seconds: None)

        assert demo_server.wipe(data_dir, attempts=5) == []
        assert len(attempts) == 2


class TestMainRefusesOnlyForTheDatabase:
    def test_a_surviving_database_stops_the_boot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A locked `.db` means another demo server is still running, and
        starting a second one on the same file is how you get two writers."""
        data_dir = tmp_path / "demo"
        monkeypatch.setattr(demo_server, "wipe", lambda _dir: [data_dir / "demo.db"])

        code = demo_server.main(["--fresh", "--data-dir", str(data_dir)])

        assert code == 1
        assert "Could not delete the demo database" in capsys.readouterr().err

    def test_a_surviving_cache_file_does_not(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A browser profile left behind is a stale cache, not state the demo
        reads. Refusing to start over one would be the bug this fixes, again."""
        data_dir = tmp_path / "demo"
        leftover = data_dir / "browser_profiles" / "user_1" / "000003.log"
        monkeypatch.setattr(demo_server, "wipe", lambda _dir: [leftover])
        started: list[str] = []
        monkeypatch.setattr(demo_server, "_run_server", lambda *a, **k: started.append("ran"))

        code = demo_server.main(["--fresh", "--data-dir", str(data_dir)])

        assert code == 0
        assert started == ["ran"]
