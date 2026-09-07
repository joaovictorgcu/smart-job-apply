"""What counts as "the form changed" between review and submission.

The fingerprint is the only thing standing between a human approving one document
and a different one being typed into a real employer's form. It has to be strict
about everything the reviewer read, and blind to everything they did not — a
false positive here refuses every submission and the product stops working, while
a false negative sends words nobody approved.
"""

from __future__ import annotations

from app.automation.contracts import FormQuestion
from app.automation.engine.answers import _form_fingerprint


def question(
    *,
    field_id: str = "urn:li:fsd_formElement:(4012345678,1111,numeric)",
    label: str = "Years of Python experience",
    options: list[str] | None = None,
    required: bool = True,
    kind: str = "number",
) -> FormQuestion:
    return FormQuestion(
        field_id=field_id,
        label=label,
        kind=kind,  # type: ignore[arg-type]
        options=list(options or []),
        required=required,
    )


class TestWhatIsIgnored:
    def test_a_rotated_dom_id_is_not_a_change(self) -> None:
        """The decision this test defends.

        LinkedIn's Easy Apply ids embed a per-form-instance URN, so re-opening the
        same posting can hand back different ids for the same questions. Hashing
        them would refuse every real submission — and the reviewer never saw a DOM
        id, so it protects nothing.
        """
        before = _form_fingerprint([question(field_id="urn:li:fsd_formElement:(1,1,numeric)")])
        after = _form_fingerprint([question(field_id="urn:li:fsd_formElement:(9,9,numeric)")])
        assert before == after

    def test_reordering_the_questions_is_not_a_change(self) -> None:
        one, two = question(label="First"), question(label="Second")
        assert _form_fingerprint([one, two]) == _form_fingerprint([two, one])

    def test_reordering_the_options_is_not_a_change(self) -> None:
        before = _form_fingerprint([question(kind="select", options=["Yes", "No"])])
        after = _form_fingerprint([question(kind="select", options=["No", "Yes"])])
        assert before == after

    def test_the_control_kind_alone_is_not_a_change(self) -> None:
        # The reviewer read the question and their answer, not the widget rendering
        # it; `_approved_answers` takes the kind from the fresh form anyway.
        before = _form_fingerprint([question(kind="text")])
        after = _form_fingerprint([question(kind="textarea")])
        assert before == after


class TestWhatCounts:
    def test_a_new_question_is_a_change(self) -> None:
        before = _form_fingerprint([question(label="Years of Python experience")])
        after = _form_fingerprint(
            [question(label="Years of Python experience"), question(label="Do you need a visa?")]
        )
        assert before != after

    def test_a_removed_question_is_a_change(self) -> None:
        before = _form_fingerprint([question(label="A"), question(label="B")])
        assert before != _form_fingerprint([question(label="A")])

    def test_a_reworded_label_is_a_change(self) -> None:
        before = _form_fingerprint([question(label="Years of Python experience")])
        after = _form_fingerprint([question(label="Years of Java experience")])
        assert before != after

    def test_a_new_option_is_a_change(self) -> None:
        before = _form_fingerprint([question(kind="select", options=["Yes", "No"])])
        after = _form_fingerprint(
            [question(kind="select", options=["Yes", "No", "Prefer not to say"])]
        )
        assert before != after

    def test_becoming_required_is_a_change(self) -> None:
        # The reviewer may have left it blank precisely because it was optional.
        before = _form_fingerprint([question(required=False)])
        assert before != _form_fingerprint([question(required=True)])


class TestShape:
    def test_it_is_a_sha256_hex_digest(self) -> None:
        digest = _form_fingerprint([question()])
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")

    def test_an_empty_form_still_hashes(self) -> None:
        # A form with no questions is a real case (resume-only Easy Apply), and it
        # must produce a value, because comparing against None always refuses.
        assert len(_form_fingerprint([])) == 64

    def test_it_is_stable_across_calls(self) -> None:
        # Compared across processes days apart, so it must not depend on hash
        # randomisation or dict ordering.
        assert _form_fingerprint([question()]) == _form_fingerprint([question()])
