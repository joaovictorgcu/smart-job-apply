"""The application flow, in a real browser, end to end.

What these tests are for: every other test in the suite replaces the browser
with `FakeLinkedInService`, so nothing exercises the selectors, the step
navigation, or the "fill but never submit" rule as *browser* behaviour. Here a
real Chromium reads real markup through the production page objects.

The assertion that matters most is `portal.submitted == []` after preparing a
draft. The fake portal records a submission only when the browser actually
clicks "Submit application", so that list is a tripwire: if any refactor makes
the filling code reach that button, this test fails and says so.
"""

from __future__ import annotations

import pytest

from app.automation.contracts import FormAnswer, SearchFilters
from app.automation.errors import (
    AlreadyAppliedError,
    EasyApplyUnavailableError,
    SecurityCheckpointError,
)
from app.automation.linkedin.service import LinkedInBrowserService
from tests.e2e.portal import (
    FakePortal,
    PortalField,
    PortalStep,
    make_jobs,
    multi_step_steps,
)

pytestmark = pytest.mark.e2e


# Answers keyed by the DOM ids the fake form uses, which is what the engine
# supplies once `open_easy_apply` has reported the questions.
FULL_ANSWERS = [
    FormAnswer(field_id="numeric-form-component-years", value="6", kind="number"),
    FormAnswer(field_id="radio-form-component-auth", value="Yes", kind="radio"),
    FormAnswer(field_id="select-form-component-english", value="Advanced", kind="select"),
]


@pytest.fixture
def multi_step_portal(portal: FakePortal) -> FakePortal:
    """The four-page form, for the tests that are about step navigation."""
    portal.steps = multi_step_steps()
    return portal


# --------------------------------------------------------------------------- #
# Session and search
# --------------------------------------------------------------------------- #


async def test_start_detects_the_logged_in_session_and_reads_the_name(
    service: LinkedInBrowserService,
) -> None:
    state = await service.start()

    assert state.browser_open is True
    assert state.logged_in is True
    assert state.blocked is False
    assert state.display_name == "Test Candidate"


async def test_start_reports_a_logged_out_portal_rather_than_guessing(
    service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.logged_in = False

    state = await service.start()

    assert state.logged_in is False
    assert state.display_name is None


async def test_search_reads_every_card_field_from_the_results_page(
    logged_in_service: LinkedInBrowserService,
) -> None:
    postings = await logged_in_service.search_jobs(
        SearchFilters(keywords="python", max_results=10, easy_apply_only=True)
    )

    assert [posting.title for posting in postings] == [
        "Backend Engineer 1",
        "Backend Engineer 2",
        "Backend Engineer 3",
    ]
    first = postings[0]
    assert first.external_id == "4010000001"
    assert first.company == "Company 1"
    assert first.location == "Remote"
    assert first.easy_apply is True
    assert first.workplace_type == "remote"
    assert first.url == "https://www.linkedin.com/jobs/view/4010000001/"


async def test_search_respects_max_results(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.jobs = make_jobs(5)

    postings = await logged_in_service.search_jobs(
        SearchFilters(keywords="python", max_results=2, easy_apply_only=True)
    )

    assert len(postings) == 2


async def test_search_skips_a_card_marked_applied(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.jobs[1].already_applied = True

    postings = await logged_in_service.search_jobs(
        SearchFilters(keywords="python", max_results=10, easy_apply_only=True)
    )

    assert [posting.external_id for posting in postings] == ["4010000001", "4010000003"]


async def test_search_returns_nothing_when_the_page_says_no_results(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.jobs = []

    postings = await logged_in_service.search_jobs(
        SearchFilters(keywords="nothing", max_results=10)
    )

    assert postings == []


async def test_job_details_are_read_from_the_detail_page(
    logged_in_service: LinkedInBrowserService,
) -> None:
    posting = await logged_in_service.fetch_job_details("4010000002")

    assert posting.title == "Backend Engineer 2"
    assert posting.company == "Company 2"
    assert posting.description is not None
    assert "FastAPI" in posting.description


# --------------------------------------------------------------------------- #
# Opening the form
# --------------------------------------------------------------------------- #


async def test_open_easy_apply_reports_the_form_it_can_see(
    logged_in_service: LinkedInBrowserService,
) -> None:
    questions = await logged_in_service.open_easy_apply("4010000001")

    by_label = {question.label: question for question in questions}
    assert set(by_label) == {
        "City",
        "Years of Python experience?",
        "Are you authorized to work in this country?",
        "Level of English",
    }
    assert by_label["City"].kind == "text"
    assert by_label["City"].current_value == "São Paulo, Brazil"
    assert by_label["Years of Python experience?"].kind == "number"
    # The file input is a resume upload, not a question to answer.
    assert "Resume" not in by_label


async def test_open_easy_apply_reports_only_the_visible_step(
    multi_step_portal: FakePortal, logged_in_service: LinkedInBrowserService
) -> None:
    """A later step's inputs stay in the DOM and must not leak into step one.

    This is also why a multi-step form cannot complete unattended: the AI is
    only ever asked about the questions reported here.
    """
    questions = await logged_in_service.open_easy_apply("4010000001")

    assert [question.label for question in questions] == ["City"]


async def test_open_easy_apply_rejects_a_posting_without_it(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.jobs = make_jobs(1, easy_apply=False)

    with pytest.raises(EasyApplyUnavailableError):
        await logged_in_service.open_easy_apply(portal.jobs[0].external_id)


async def test_open_easy_apply_rejects_a_posting_already_applied_to(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.jobs[0].already_applied = True

    with pytest.raises(AlreadyAppliedError):
        await logged_in_service.open_easy_apply("4010000001")


# --------------------------------------------------------------------------- #
# Filling — the assisted-mode guarantee
# --------------------------------------------------------------------------- #


async def test_filling_walks_every_step_and_stops_without_submitting(
    multi_step_portal: FakePortal, logged_in_service: LinkedInBrowserService
) -> None:
    """The core guarantee, asserted at the browser level.

    On the four-page form, so it also covers Next -> Next -> Review navigation.
    """
    portal = multi_step_portal
    await logged_in_service.open_easy_apply("4010000001")
    draft = await logged_in_service.fill_and_advance(
        FULL_ANSWERS, cover_letter="I would like to apply for this role."
    )

    assert draft.ready_to_submit is True
    assert draft.cover_letter_attached is True
    # Nothing was sent: the portal records a submission only on a real click of
    # "Submit application", and nothing here is allowed to click it.
    assert portal.submitted == []

    answered = {answer.field_id: answer.value for answer in draft.answers}
    assert answered["numeric-form-component-years"] == "6"
    assert answered["radio-form-component-auth"] == "Yes"
    assert answered["select-form-component-english"] == "Advanced"
    assert "would like to apply" in answered["textarea-form-component-letter"]

    # Every step's questions accumulate into the draft, not just the last one's.
    labels = {question.label for question in draft.questions}
    assert {"City", "Years of Python experience?", "Cover letter"} <= labels


async def test_filling_uploads_the_resume_when_the_form_asks_for_a_file(
    browser_session,  # noqa: ANN001 - fixture, typed by conftest
    portal: FakePortal,
    fast_throttle,  # noqa: ANN001 - fixture, typed by conftest
    tmp_path,  # noqa: ANN001 - pytest builtin
) -> None:
    from tests.e2e.portal import install

    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fake resume\n")

    await install(browser_session.context, portal)
    service = LinkedInBrowserService(
        user_id=1,
        throttle=fast_throttle,
        browser=browser_session,
        resume_path=str(resume),
    )
    await service.start()

    await service.open_easy_apply("4010000001")
    draft = await service.fill_and_advance(FULL_ANSWERS)

    assert draft.resume_attached is True
    assert draft.ready_to_submit is True
    assert portal.submitted == []


async def test_a_required_field_with_no_answer_stops_the_draft(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    """No answer for a required question means the human has to finish it."""
    await logged_in_service.open_easy_apply("4010000001")

    # The radio group and the select are answered; the required number is not.
    draft = await logged_in_service.fill_and_advance(
        [answer for answer in FULL_ANSWERS if answer.kind != "number"]
    )

    assert draft.ready_to_submit is False
    assert portal.submitted == []
    unanswered = [question.label for question in draft.unanswered]
    assert "Years of Python experience?" in unanswered
    assert any("need a human answer" in note for note in draft.notes)


async def test_an_unfillable_answer_is_reported_not_forced(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    """A select value the form does not offer cannot be chosen, and says so."""
    await logged_in_service.open_easy_apply("4010000001")
    draft = await logged_in_service.fill_and_advance(
        [
            FormAnswer(field_id="numeric-form-component-years", value="6", kind="number"),
            FormAnswer(field_id="radio-form-component-auth", value="Yes", kind="radio"),
            FormAnswer(
                field_id="select-form-component-english",
                value="Klingon (native)",
                kind="select",
            ),
        ]
    )

    assert draft.ready_to_submit is False
    assert portal.submitted == []
    assert "Level of English" in [question.label for question in draft.unanswered]


async def test_the_form_reports_which_questions_are_required(
    logged_in_service: LinkedInBrowserService,
) -> None:
    await logged_in_service.open_easy_apply("4010000001")
    draft = await logged_in_service.fill_and_advance(FULL_ANSWERS)

    by_label = {question.label: question for question in draft.questions}
    assert by_label["Years of Python experience?"].required is True
    assert by_label["Are you authorized to work in this country?"].required is True
    # A plain optional field must not be marked required, or every draft would
    # look blocked.
    assert by_label["City"].required is False


async def test_a_question_the_automation_never_saw_is_still_reported(
    multi_step_portal: FakePortal, logged_in_service: LinkedInBrowserService
) -> None:
    """The multi-step consequence, made explicit.

    With answers only for the first step, the later steps' required fields come
    back as unanswered rather than being skipped or guessed — which is what
    makes the review gate trustworthy on a form the AI could not fully see.
    """
    await logged_in_service.open_easy_apply("4010000001")
    draft = await logged_in_service.fill_and_advance([])

    assert draft.ready_to_submit is False
    assert multi_step_portal.submitted == []
    unanswered = [question.label for question in draft.unanswered]
    assert "Years of Python experience?" in unanswered


async def test_radio_and_select_options_are_read_from_the_markup(
    logged_in_service: LinkedInBrowserService,
) -> None:
    await logged_in_service.open_easy_apply("4010000001")
    draft = await logged_in_service.fill_and_advance(FULL_ANSWERS)

    by_label = {question.label: question for question in draft.questions}
    assert by_label["Are you authorized to work in this country?"].options == ["Yes", "No"]
    # The "Select an option" placeholder is not a real choice.
    assert by_label["Level of English"].options == ["Basic", "Intermediate", "Advanced"]


async def test_the_follow_company_checkbox_is_left_alone(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    """LinkedIn pre-checks it; that is the user's choice to make, not ours."""
    portal.steps = (
        PortalStep(
            fields=(
                PortalField("follow-company-checkbox", "Follow Company 1", "checkbox"),
                PortalField("single-line-text-form-component-city", "City", "text"),
            )
        ),
        PortalStep(review=True),
    )

    questions = await logged_in_service.open_easy_apply("4010000001")

    assert [question.label for question in questions] == ["City"]


# --------------------------------------------------------------------------- #
# Submitting — only ever explicitly
# --------------------------------------------------------------------------- #


async def test_submit_sends_the_application_and_confirms_it(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    await logged_in_service.open_easy_apply("4010000001")
    draft = await logged_in_service.fill_and_advance(FULL_ANSWERS)
    assert draft.ready_to_submit is True

    confirmed = await logged_in_service.submit()

    assert confirmed is True
    assert portal.submitted == ["4010000001"]
    # The answers that reached the form are the ones that were approved.
    sent = portal.submitted_payloads[0]
    assert sent["numeric-form-component-years"] == "6"
    assert sent["radio-form-component-auth"] == "Yes"


async def test_submit_before_the_review_step_is_refused(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    """The submit button does not exist yet, and that has to be an error."""
    from app.automation.errors import UnexpectedPageError

    await logged_in_service.open_easy_apply("4010000001")

    with pytest.raises(UnexpectedPageError):
        await logged_in_service.submit()
    assert portal.submitted == []


async def test_discard_closes_the_draft_without_sending_it(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    await logged_in_service.open_easy_apply("4010000001")
    await logged_in_service.fill_and_advance(FULL_ANSWERS)

    await logged_in_service.discard()

    assert logged_in_service.has_open_draft() is False
    assert portal.submitted == []


async def test_preparing_many_jobs_submits_none_of_them(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    """The batch case: three drafts prepared, zero applications sent."""
    portal.jobs = make_jobs(3)

    for job in portal.jobs:
        await logged_in_service.open_easy_apply(job.external_id)
        draft = await logged_in_service.fill_and_advance(FULL_ANSWERS)
        assert draft.ready_to_submit is True
        await logged_in_service.discard()

    assert portal.submitted == []


# --------------------------------------------------------------------------- #
# Security challenges
# --------------------------------------------------------------------------- #


async def test_a_challenge_page_stops_the_search_instead_of_working_around_it(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.checkpoint_paths = ("/jobs/search",)

    with pytest.raises(SecurityCheckpointError):
        await logged_in_service.search_jobs(
            SearchFilters(keywords="python", max_results=5)
        )

    state = await logged_in_service.get_state()
    assert state.blocked is True
    assert state.blocked_reason is not None


async def test_a_challenge_during_the_apply_flow_stops_before_any_submission(
    logged_in_service: LinkedInBrowserService, portal: FakePortal
) -> None:
    portal.checkpoint_paths = ("/jobs/view",)

    with pytest.raises(SecurityCheckpointError):
        await logged_in_service.open_easy_apply("4010000001")

    assert portal.submitted == []
