"""Your resume, and the one this vacancy gets.

The feature's claim is not "it adapted the resume" — it is "it adapted the
resume *this little*". So what is pinned here is the budget: how many edits the
copy carries, which position moved where, and that the invention count is
measured rather than assumed.
"""

from __future__ import annotations

from app.domain.resume_diff import Snapshot, SnapshotExperience, compare

MASTER_IDS = [1, 2, 3]
MASTER_SKILLS = ["Python", "PostgreSQL", "React", "Docker"]
MASTER_TEXT = (
    "Desenvolvedor Full Stack. Construí APIs em Python e FastAPI sobre PostgreSQL. "
    "Painéis em React. Deploy com Docker."
)


def snapshot(**overrides: object) -> Snapshot:
    payload: dict[str, object] = {
        "summary": "Desenvolvedor Full Stack.",
        "skills": tuple(MASTER_SKILLS),
        "emphasized_technologies": ("Python",),
        "experiences": (
            SnapshotExperience(experience_id=1, company="Acme", role="Dev"),
            SnapshotExperience(experience_id=2, company="Globex", role="Dev"),
            SnapshotExperience(experience_id=3, company="Initech", role="Dev"),
        ),
    }
    payload.update(overrides)
    return Snapshot(**payload)  # type: ignore[arg-type]


def run(**overrides: object):
    payload: dict[str, object] = {
        "master_experience_ids": MASTER_IDS,
        "master_skills": MASTER_SKILLS,
        "master_text": MASTER_TEXT,
        "snapshot": snapshot(),
    }
    payload.update(overrides)
    return compare(**payload)  # type: ignore[arg-type]


class TestTheChangeBudget:
    def test_an_untouched_copy_reports_no_changes_at_all(self) -> None:
        result = run()

        assert result.changes_total == 0
        assert result.experiences_reordered == 0
        assert result.sections_adjusted == 0
        assert result.highlighted_technologies == ()

    def test_a_reordered_experience_counts_once_and_says_where_it_came_from(self) -> None:
        result = run(
            snapshot=snapshot(
                experiences=(
                    SnapshotExperience(experience_id=3, company="Initech", role="Dev"),
                    SnapshotExperience(experience_id=1, company="Acme", role="Dev"),
                    SnapshotExperience(experience_id=2, company="Globex", role="Dev"),
                )
            )
        )

        assert result.experiences_reordered == 3
        promoted = result.moves[0]
        assert (promoted.company, promoted.from_position, promoted.to_position) == (
            "Initech",
            3,
            1,
        )

    def test_a_technology_that_came_forward_is_named(self) -> None:
        result = run(snapshot=snapshot(skills=("React", "Python", "PostgreSQL", "Docker")))

        assert result.highlighted_technologies == ("React",)
        assert result.changes_total == 1

    def test_a_technology_that_slipped_down_is_not_reported_twice(self) -> None:
        # React moved up, so Python and PostgreSQL moved down. Reporting those
        # would double every highlight.
        result = run(snapshot=snapshot(skills=("React", "Python", "PostgreSQL", "Docker")))

        assert "Python" not in result.highlighted_technologies

    def test_promoted_sentences_count_as_one_adjusted_section_each(self) -> None:
        result = run(
            snapshot=snapshot(
                experiences=(
                    SnapshotExperience(experience_id=1, company="Acme", role="Dev", promoted=2),
                    SnapshotExperience(experience_id=2, company="Globex", role="Dev"),
                    SnapshotExperience(experience_id=3, company="Initech", role="Dev"),
                )
            )
        )

        assert result.sections_adjusted == 1
        assert result.promoted_bullets == 2
        assert result.changes_total == 1


class TestNothingIsInvented:
    def test_a_clean_copy_measures_zero_rather_than_assuming_it(self) -> None:
        result = run()

        assert result.invented == ()
        assert result.is_clean is True

    def test_a_technology_the_master_never_named_is_flagged(self) -> None:
        result = run(
            snapshot=snapshot(
                experiences=(
                    SnapshotExperience(
                        experience_id=1,
                        company="Acme",
                        role="Dev",
                        technologies=("Kubernetes",),
                    ),
                    SnapshotExperience(experience_id=2, company="Globex", role="Dev"),
                    SnapshotExperience(experience_id=3, company="Initech", role="Dev"),
                )
            )
        )

        assert "Kubernetes" in result.invented
        assert result.is_clean is False

    def test_the_guard_reads_every_part_of_the_document(self) -> None:
        # Not only the technologies list: a fabricated tool in a bullet is the
        # one that would actually be read by an employer.
        result = run(
            snapshot=snapshot(
                experiences=(
                    SnapshotExperience(
                        experience_id=1,
                        company="Acme",
                        role="Dev",
                        responsibilities=("Orquestrei serviços com Kubernetes.",),
                    ),
                    SnapshotExperience(experience_id=2, company="Globex", role="Dev"),
                    SnapshotExperience(experience_id=3, company="Initech", role="Dev"),
                )
            )
        )

        assert "Kubernetes" in result.invented


class TestWhenItCannotBeCompared:
    def test_a_stale_copy_reports_nothing_rather_than_the_user_s_own_edits(self) -> None:
        result = run(is_comparable=False)

        assert result.is_comparable is False
        assert result.moves == ()
        assert result.changes_total == 0

    def test_a_position_the_master_no_longer_has_is_not_a_move(self) -> None:
        # Deleted from the profile after this copy was frozen. The copy keeping
        # it is documented behaviour, not something the adaptation did.
        result = run(master_experience_ids=[1, 2])

        assert [move.experience_id for move in result.moves] == [1, 2]
