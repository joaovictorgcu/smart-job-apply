"""The guards must be able to fail.

`tools/guards.py` is the machine-checked half of this project's safety story, and
a guard suite that only ever passes is decoration: it produces a green check for
free, and everyone stops reading it. So every test below writes a deliberately
offending file into `tmp_path` and asserts the guard actually reports it, with the
right guard id and the right line. The last piece is the mirror image — the live
repository passes all seven today, which is what turns the checks into a ratchet.

The module is loaded by path rather than imported: `tools/` is not a package and
must never become one, because CI runs `python tools/guards.py` with nothing
installed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GUARDS_PATH = REPO_ROOT / "tools" / "guards.py"


def _load_guards() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guards_under_test", GUARDS_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {GUARDS_PATH}"
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves its string annotations through `sys.modules[__module__]`,
    # so the module has to be registered before it executes, not after.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guards = _load_guards()

# A minimal but *compliant* pair of anchor files, so a fake repository starts out
# passing G1 and G2 and each test only introduces the one violation it is about.
COMPLIANT_CONFIG = """
class Settings(BaseSettings):
    headless: bool = False
    assisted_mode_only: bool = True
"""

COMPLIANT_USER_MODEL = """
class UserSettings(Base, TimestampMixin):
    daily_cap: Mapped[int] = mapped_column(Integer, default=15)
    require_manual_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repository whose layout the guards recognise."""
    app = tmp_path / "backend" / "app"
    (app / "models").mkdir(parents=True)
    (app / "config.py").write_text(COMPLIANT_CONFIG, encoding="utf-8")
    (app / "models" / "user.py").write_text(COMPLIANT_USER_MODEL, encoding="utf-8")
    return tmp_path


def write(repo: Path, relative_path: str, source: str) -> None:
    path = repo / "backend" / "app" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def ids(violations: list) -> set[str]:
    return {violation.guard for violation in violations}


class TestTheLiveRepository:
    """The ratchet: main + branch are clean today, so any new violation is new."""

    def test_every_guard_passes_on_this_repository(self) -> None:
        violations = guards.run_all(REPO_ROOT)
        assert not violations, "\n".join(violation.render() for violation in violations)

    def test_main_exits_zero_and_says_so(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert guards.main([str(REPO_ROOT)]) == 0
        assert f"All {len(guards.ALL_GUARDS)} guards passed." in capsys.readouterr().out

    def test_the_default_root_is_the_repository_root(self) -> None:
        # A wrong default would make the CI job scan an empty tree and pass.
        assert guards.default_root() == REPO_ROOT

    def test_every_guard_is_wired_into_the_runner(self) -> None:
        # A guard defined but never registered is worse than no guard at all.
        defined = {name for name in vars(guards) if name.startswith("g") and name[1:2].isdigit()}
        assert {guard.__name__ for guard in guards.ALL_GUARDS} == defined
        assert len(guards.ALL_GUARDS) == 7

    def test_a_compliant_fake_repository_reports_nothing(self, repo: Path) -> None:
        assert guards.run_all(repo) == []


class TestG1AssistedMode:
    def test_a_flipped_default_is_reported(self, repo: Path) -> None:
        flipped = COMPLIANT_CONFIG.replace("only: bool = True", "only: bool = False")
        write(repo, "config.py", flipped)
        violations = guards.g1_assisted_mode_default(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G1"
        assert violations[0].path == "backend/app/config.py"
        assert violations[0].line == 4

    def test_a_removed_field_is_reported(self, repo: Path) -> None:
        # Renaming the setting must break the build, not disable the check.
        write(repo, "config.py", "class Settings(BaseSettings):\n    headless: bool = False\n")
        assert ids(guards.g1_assisted_mode_default(repo)) == {"G1"}

    def test_a_missing_settings_class_is_reported(self, repo: Path) -> None:
        write(repo, "config.py", "VALUE = 1\n")
        assert ids(guards.g1_assisted_mode_default(repo)) == {"G1"}


class TestG2UserSettingsDefaults:
    def test_a_flipped_dry_run_default_is_reported(self, repo: Path) -> None:
        write(
            repo,
            "models/user.py",
            COMPLIANT_USER_MODEL.replace(
                "dry_run: Mapped[bool] = mapped_column(Boolean, default=True)",
                "dry_run: Mapped[bool] = mapped_column(Boolean, default=False)",
            ),
        )
        violations = guards.g2_user_settings_defaults(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G2"
        assert "dry_run" in violations[0].message

    def test_a_flipped_approval_default_is_reported(self, repo: Path) -> None:
        write(
            repo,
            "models/user.py",
            COMPLIANT_USER_MODEL.replace(
                "require_manual_approval: Mapped[bool] = mapped_column(Boolean, default=True)",
                "require_manual_approval: Mapped[bool] = mapped_column(Boolean, default=False)",
            ),
        )
        violations = guards.g2_user_settings_defaults(repo)
        assert len(violations) == 1
        assert "require_manual_approval" in violations[0].message

    def test_both_flipped_are_reported_separately(self, repo: Path) -> None:
        write(
            repo,
            "models/user.py",
            COMPLIANT_USER_MODEL.replace("default=True)", "default=False)"),
        )
        assert len(guards.g2_user_settings_defaults(repo)) == 2

    def test_a_default_hidden_behind_a_helper_is_reported(self, repo: Path) -> None:
        # An unreadable default is treated as a failure, never as a pass.
        write(
            repo,
            "models/user.py",
            COMPLIANT_USER_MODEL.replace("default=True)\n", "default=_flag())\n", 1),
        )
        assert ids(guards.g2_user_settings_defaults(repo)) == {"G2"}

    def test_a_dropped_column_is_reported(self, repo: Path) -> None:
        write(repo, "models/user.py", "class UserSettings(Base):\n    pass\n")
        assert len(guards.g2_user_settings_defaults(repo)) == 2


class TestG3SubmitCallSites:
    OFFENDER = """
async def apply_now(service):
    return await service.submit()
"""

    def test_a_submit_outside_the_engine_is_reported(self, repo: Path) -> None:
        write(repo, "services/automation_service.py", self.OFFENDER)
        violations = guards.g3_submit_call_sites(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G3"
        assert violations[0].path == "backend/app/services/automation_service.py"
        assert violations[0].line == 3
        # The message names the receiver, so the reader knows what to go and look at.
        assert "`service.submit()`" in violations[0].message

    def test_a_synchronous_call_is_reported_too(self, repo: Path) -> None:
        # Wrapping the coroutine does not put the approval check back.
        write(repo, "api/routes/automation.py", "def go(service):\n    service.submit()\n")
        assert ids(guards.g3_submit_call_sites(repo)) == {"G3"}

    def test_the_engine_module_is_allowed(self, repo: Path) -> None:
        write(repo, "automation/engine.py", self.OFFENDER)
        assert guards.g3_submit_call_sites(repo) == []

    def test_the_engine_package_layout_is_allowed(self, repo: Path) -> None:
        # Another agent is splitting engine.py into a package; both must pass.
        write(repo, "automation/engine/submit.py", self.OFFENDER)
        assert guards.g3_submit_call_sites(repo) == []

    def test_the_linkedin_service_and_apply_are_allowed(self, repo: Path) -> None:
        write(repo, "automation/linkedin/service.py", self.OFFENDER)
        write(repo, "automation/linkedin/apply.py", self.OFFENDER)
        assert guards.g3_submit_call_sites(repo) == []

    def test_similarly_named_attributes_are_ignored(self, repo: Path) -> None:
        write(
            repo,
            "services/stats_service.py",
            "def counts(repo, draft):\n"
            "    repo.submitted_today()\n"
            "    repo.submitted_last_days(7)\n"
            "    repo.submit_application()\n"
            "    return draft.ready_to_submit\n",
        )
        assert guards.g3_submit_call_sites(repo) == []


class TestG4PlaywrightImports:
    def test_an_import_outside_the_adapter_is_reported(self, repo: Path) -> None:
        write(repo, "services/job_service.py", "from playwright.async_api import Page\n")
        violations = guards.g4_playwright_imports(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G4"
        assert violations[0].line == 1

    def test_a_plain_import_is_reported(self, repo: Path) -> None:
        write(repo, "api/deps.py", "import playwright\n")
        assert ids(guards.g4_playwright_imports(repo)) == {"G4"}

    def test_the_browser_adapter_and_linkedin_package_are_allowed(self, repo: Path) -> None:
        write(repo, "automation/browser.py", "from playwright.async_api import async_playwright\n")
        write(repo, "automation/linkedin/search.py", "from playwright.async_api import Locator\n")
        assert guards.g4_playwright_imports(repo) == []

    def test_the_word_in_a_string_is_not_an_import(self, repo: Path) -> None:
        # app/ai/client.py lists "playwright" as a skill keyword; a grep-based
        # guard would flag it, which is why this walks the AST.
        write(repo, "ai/client.py", 'SKILLS = ["playwright", "selenium"]\n')
        assert guards.g4_playwright_imports(repo) == []


class TestG5DomainPurity:
    @pytest.mark.parametrize(
        "source",
        [
            "from sqlalchemy import select\n",
            "import anthropic\n",
            "from playwright.async_api import Page\n",
            "from fastapi import Depends\n",
            "from app.models import Application\n",
        ],
    )
    def test_an_io_import_in_the_domain_is_reported(self, repo: Path, source: str) -> None:
        write(repo, "domain/scoring.py", source)
        violations = guards.g5_domain_purity(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G5"
        assert violations[0].path == "backend/app/domain/scoring.py"

    def test_a_pure_module_passes(self, repo: Path) -> None:
        write(
            repo,
            "domain/language.py",
            "import re\nfrom dataclasses import dataclass\nfrom app.ai.schemas import JobScore\n",
        )
        assert guards.g5_domain_purity(repo) == []


class TestG6SilentBroadExcept:
    @pytest.mark.parametrize("package", ["domain", "ai"])
    def test_a_silent_broad_catch_is_reported(self, repo: Path, package: str) -> None:
        write(
            repo,
            f"{package}/scoring.py",
            "def score(job):\n"
            "    try:\n"
            "        return compute(job)\n"
            "    except Exception:\n"
            "        return None\n",
        )
        violations = guards.g6_silent_broad_except(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G6"
        assert violations[0].line == 4

    def test_a_bare_except_is_reported(self, repo: Path) -> None:
        write(repo, "ai/client.py", "try:\n    call()\nexcept:\n    pass\n")
        assert ids(guards.g6_silent_broad_except(repo)) == {"G6"}

    def test_a_tuple_containing_exception_is_reported(self, repo: Path) -> None:
        write(repo, "ai/client.py", "try:\n    call()\nexcept (ValueError, Exception):\n    pass\n")
        assert ids(guards.g6_silent_broad_except(repo)) == {"G6"}

    def test_re_raising_is_accepted(self, repo: Path) -> None:
        write(repo, "ai/client.py", "try:\n    call()\nexcept Exception:\n    raise\n")
        assert guards.g6_silent_broad_except(repo) == []

    def test_logging_before_swallowing_is_accepted(self, repo: Path) -> None:
        write(
            repo,
            "ai/scoring.py",
            "try:\n"
            "    call()\n"
            "except Exception as exc:\n"
            '    logger.warning("AI call failed.", extra={"action": "ai.score.failed"})\n'
            "    return None\n",
        )
        assert guards.g6_silent_broad_except(repo) == []

    def test_a_narrow_catch_is_not_the_guard_s_business(self, repo: Path) -> None:
        write(repo, "ai/scoring.py", "try:\n    call()\nexcept ValueError:\n    return None\n")
        assert guards.g6_silent_broad_except(repo) == []

    def test_other_packages_are_out_of_scope(self, repo: Path) -> None:
        # The guard is deliberately narrow: those two packages are where a
        # swallowed error is invisible because nothing downstream notices.
        write(repo, "services/job_service.py", "try:\n    call()\nexcept Exception:\n    pass\n")
        assert guards.g6_silent_broad_except(repo) == []


class TestG7ReservedLogKeys:
    def test_a_reserved_key_is_reported(self, repo: Path) -> None:
        write(repo, "services/user_service.py", 'log.info("x", extra={"filename": "cv.pdf"})\n')
        violations = guards.g7_reserved_log_keys(repo)
        assert len(violations) == 1
        assert violations[0].guard == "G7"
        assert violations[0].line == 1
        assert "filename" in violations[0].message

    @pytest.mark.parametrize("key", ["message", "asctime", "module", "name", "args"])
    def test_the_reserved_set_comes_from_a_real_log_record(self, repo: Path, key: str) -> None:
        assert key in guards.reserved_record_attributes()
        write(repo, "api/errors.py", f'log.error("x", extra={{{key!r}: 1}})\n')
        assert ids(guards.g7_reserved_log_keys(repo)) == {"G7"}

    def test_the_fields_this_codebase_actually_uses_are_fine(self, repo: Path) -> None:
        write(
            repo,
            "automation/engine.py",
            'log.info("x", extra={"action": "engine.submit", "user_id": 1, "run_id": 2})\n',
        )
        assert guards.g7_reserved_log_keys(repo) == []


class TestTheCommandLine:
    def test_a_violation_is_printed_and_exits_one(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "services/automation_service.py", "async def go(s):\n    await s.submit()\n")
        assert guards.main([str(repo)]) == 1
        out = capsys.readouterr().out
        assert "GUARD G3 FAILED  backend/app/services/automation_service.py:2" in out
        assert "1 violation(s) across 1 guard(s)." in out

    def test_unparsable_source_fails_instead_of_passing(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "services/broken.py", "def (:\n")
        assert guards.main([str(repo)]) == 1
        assert "GUARD SETUP FAILED" in capsys.readouterr().out
