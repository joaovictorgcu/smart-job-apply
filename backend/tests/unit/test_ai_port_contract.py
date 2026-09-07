"""The contract between the engine's AI seam and `app.ai.scoring`.

The seam used to be resolved by import name and bound by parameter name at call
time, so a renamed parameter — or a function that simply was not there — turned
into "the AI never ran" instead of into a failure. These tests pin the shape of
`AIOrchestrator`, its `app.ai.scoring` implementation, and the module-level
functions behind it, so the next rename breaks here rather than in production.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from app.ai import scoring
from app.ai.port import AIOrchestrator, ScoringOrchestrator, get_orchestrator

# Every orchestrator method, mapped to the `app.ai.scoring` function behind it.
DELEGATIONS: dict[str, str] = {
    "analyze_job": "analyze_job",
    "generate_cover_letter": "generate_cover_letter",
    "answer_screening": "answer_screening",
}


def parameters(func: Callable[..., Any], *, drop_self: bool = False) -> list[tuple[str, Any]]:
    """(name, kind) pairs, optionally without the bound `self`."""
    pairs = [
        (parameter.name, parameter.kind)
        for parameter in inspect.signature(func).parameters.values()
    ]
    return pairs[1:] if drop_self else pairs


def required_parameters(func: Callable[..., Any]) -> list[tuple[str, Any]]:
    """(name, kind) pairs the caller must supply — everything without a default."""
    return [
        (parameter.name, parameter.kind)
        for parameter in inspect.signature(func).parameters.values()
        if parameter.default is inspect.Parameter.empty
    ]


class TestTheProtocolDescribesItsImplementation:
    def test_the_protocol_declares_exactly_the_delegated_methods(self) -> None:
        assert set(AIOrchestrator.__protocol_attrs__) == set(DELEGATIONS)

    def test_the_scoring_orchestrator_satisfies_the_protocol(self) -> None:
        assert isinstance(ScoringOrchestrator(), AIOrchestrator)

    def test_the_default_orchestrator_satisfies_the_protocol(self) -> None:
        assert isinstance(get_orchestrator(), AIOrchestrator)

    @pytest.mark.parametrize("method_name", sorted(DELEGATIONS))
    def test_the_implementation_matches_the_declared_signature(self, method_name: str) -> None:
        declared = parameters(getattr(AIOrchestrator, method_name), drop_self=True)
        implemented = parameters(getattr(ScoringOrchestrator, method_name), drop_self=True)
        assert implemented == declared

    @pytest.mark.parametrize("method_name", sorted(DELEGATIONS))
    def test_every_method_is_a_coroutine(self, method_name: str) -> None:
        assert inspect.iscoroutinefunction(getattr(ScoringOrchestrator, method_name))


class TestTheDelegationCanActuallyBind:
    @pytest.mark.parametrize(("method_name", "function_name"), sorted(DELEGATIONS.items()))
    def test_the_orchestrator_supplies_every_required_argument(
        self, method_name: str, function_name: str
    ) -> None:
        """The exact class of bug that broke this seam: names that do not line up."""
        target = getattr(scoring, function_name)
        assert parameters(getattr(ScoringOrchestrator, method_name), drop_self=True) == (
            required_parameters(target)
        )

    @pytest.mark.parametrize(("method_name", "function_name"), sorted(DELEGATIONS.items()))
    def test_no_orchestrator_argument_is_unknown_to_the_function(
        self, method_name: str, function_name: str
    ) -> None:
        declared = dict(parameters(getattr(ScoringOrchestrator, method_name), drop_self=True))
        target = dict(parameters(getattr(scoring, function_name)))
        for name, kind in declared.items():
            assert name in target, f"{function_name} has no parameter named {name!r}"
            assert target[name] == kind


class TestTheNamesTheEngineUsedToGuess:
    def test_screening_is_called_answer_screening(self) -> None:
        """`answer_screening_questions` never existed; resolving it found nothing."""
        assert hasattr(scoring, "answer_screening")
        assert not hasattr(scoring, "answer_screening_questions")

    def test_scoring_is_called_analyze_job(self) -> None:
        assert hasattr(scoring, "analyze_job")
        assert not hasattr(scoring, "score_job")

    @pytest.mark.parametrize("function_name", sorted(set(DELEGATIONS.values())))
    def test_each_delegated_function_is_public(self, function_name: str) -> None:
        assert function_name in scoring.__all__
