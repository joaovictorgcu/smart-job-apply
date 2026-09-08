"""The technology vocabulary, and how to find it in free text.

This lived inside `app.ai.client` while its only consumer was the invention
guard. It is domain knowledge, not client knowledge: the per-application resume
derivation (`app.domain.resume`) needs the same vocabulary to decide which of a
candidate's technologies a posting is actually asking about, and two copies of
this list would drift apart within a release.

Nothing here is exhaustive by design. `KNOWN_TECHNOLOGIES` is the high-signal
core; `CAMELCASE` and `ALNUM_TOKEN` catch the long tail structurally (FastAPI,
OAuth2, S3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from app.domain.language import fold

# Common technologies whose presence in a tailored resume but absence from the
# source is the clearest, most checkable sign of invention. Stored folded, which
# is why `c#` and `.net` appear in that shape: `fold` keeps `#` and `.`.
KNOWN_TECHNOLOGIES = frozenset(
    {
        "python", "java", "javascript", "typescript", "golang", "rust", "ruby",
        "php", "kotlin", "swift", "scala", "elixir", "clojure", "haskell", "perl",
        "django", "flask", "fastapi", "rails", "laravel", "spring", "express",
        "nestjs", "react", "angular", "vue", "svelte", "nextjs", "nuxt", "jquery",
        "node", "deno", "bun", "graphql", "grpc", "rest", "soap", "webpack", "vite",
        "postgresql", "postgres", "mysql", "mariadb", "sqlite", "oracle", "mongodb",
        "redis", "cassandra", "elasticsearch", "dynamodb", "snowflake", "clickhouse",
        "kafka", "rabbitmq", "celery", "airflow", "spark", "hadoop", "flink", "dbt",
        "docker", "kubernetes", "terraform", "ansible", "puppet", "chef", "helm",
        "jenkins", "gitlab", "github", "circleci", "argocd", "prometheus", "grafana",
        "aws", "azure", "gcp", "heroku", "vercel", "netlify", "cloudflare", "lambda",
        "tensorflow", "pytorch", "keras", "sklearn", "pandas", "numpy", "scipy",
        "kubeflow", "mlflow", "langchain", "opencv", "huggingface", "transformers",
        "playwright", "selenium", "cypress", "jest", "pytest", "junit", "mocha",
        "linux", "bash", "nginx", "apache", "kong", "istio", "consul", "vault",
        "git", "jira", "confluence", "figma", "tableau", "powerbi", "looker",
        "sql", "nosql", "html", "css", "sass", "tailwind", "bootstrap", "wasm",
        # The .NET half of the industry, which the original list did not cover and
        # which this feature's whole demonstration turns on.
        "c#", "csharp", ".net", "dotnet", "asp.net", "aspnet", "blazor", "linq",
        "dapper", "signalr", "xunit", "nunit", "wpf", "winforms", "maui",
        "entity framework", "sql server", "sqlserver", "nuget", "azure devops",
    }
)

# CamelCase like FastAPI, PostgreSQL, JavaScript, GraphQL.
CAMELCASE = re.compile(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z]*\b")
# Alphanumeric tokens like S3, OAuth2, Python3, k8s, EC2, gpt4 — almost always tech.
ALNUM_TOKEN = re.compile(r"\b(?:[A-Za-z]+\d+[A-Za-z\d]*|\d+[A-Za-z]+[A-Za-z\d]*)\b")
# A word token, allowing an internal `.`/`+`/`#` (node.js, asp.net) but never a
# trailing one — otherwise "Kubernetes." captures the sentence period and no longer
# matches a known technology.
ALPHA_WORD = re.compile(r"[a-z][a-z0-9]*(?:[.+#][a-z0-9]+)*")
# Same shape, original-cased, so a flagged term keeps the casing the model wrote.
ORIG_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.+#][A-Za-z0-9]+)*")


@lru_cache(maxsize=2048)
def _term_pattern(folded_term: str) -> re.Pattern[str]:
    """Whole-term matcher for an already-folded term.

    A plain `\\b` boundary is wrong for this vocabulary: `\\bc#\\b` never matches
    because `#` is itself a non-word character, and `\\b.net\\b` fails on the
    leading dot. Guarding on alphanumeric neighbours instead makes `c#`, `.net`
    and `entity framework` behave like the single words they are, while still
    refusing to match `net` inside `network`.
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])")


def position_of(haystack: str, term: str) -> int | None:
    """Index of the first whole-term occurrence of `term`, or None."""
    folded = fold(term).strip()
    if not folded:
        return None
    match = _term_pattern(folded).search(fold(haystack))
    return match.start() if match is not None else None


def mentions(haystack: str, term: str) -> bool:
    """Whether `haystack` names `term` — the one relevance test used everywhere."""
    return position_of(haystack, term) is not None


def mentioned_terms(haystack: str, vocabulary: Iterable[str]) -> list[str]:
    """The vocabulary terms `haystack` names, in the order it first names them.

    Casing comes from the vocabulary, not the haystack: these end up rendered in
    the candidate's resume, where "PostgreSQL" and "postgresql" are not
    interchangeable. Duplicate spellings of one term collapse to the first given.
    """
    found: dict[str, tuple[int, int, str]] = {}
    for rank, term in enumerate(vocabulary):
        folded = fold(term).strip()
        if not folded or folded in found:
            continue
        position = position_of(haystack, term)
        if position is not None:
            found[folded] = (position, rank, term)
    return [term for _, _, term in sorted(found.values())]


@lru_cache(maxsize=2048)
def _original_pattern(folded_term: str) -> re.Pattern[str]:
    """`_term_pattern`'s rule, applied to text that has not been folded."""
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(folded_term)}(?![A-Za-z0-9])", re.IGNORECASE
    )


def spelling_in(haystack: str, term: str) -> str:
    """How `haystack` itself spells `term`, or `term` unchanged.

    `mentioned_terms` deliberately takes casing from the vocabulary, so the
    candidate's own spelling wins for anything they have. That leaves the terms
    they do *not* have falling back to `KNOWN_TECHNOLOGIES`, which is lowercase
    throughout — so a gap renders as "elixir", "grpc", "apache" beside a posting
    that wrote "Elixir", "gRPC", "Apache". This recovers the posting's spelling
    for exactly that case.

    Matched against the unfolded text, rather than by mapping an index back out
    of `fold`, because folding is not guaranteed length-preserving. A term whose
    only difference from the haystack is an accent therefore will not match here
    and keeps its vocabulary spelling; no technology name in the vocabulary is
    accented, so that costs nothing.
    """
    folded = fold(term).strip()
    if not folded:
        return term
    match = _original_pattern(folded).search(haystack)
    return match.group(0) if match is not None else term


def job_technologies(text: str, extra_vocabulary: Iterable[str] = ()) -> list[str]:
    """The technologies a posting names, ordered by where it first names them.

    Restricted to the known vocabulary plus whatever the candidate's own resume
    calls a technology (`extra_vocabulary`, which comes first so the candidate's
    own spelling wins). A posting is mostly prose about benefits and culture, and
    a purely structural scan of it returns the company name and half the
    boilerplate — useful as an invention *flag*, useless as "what this job asks
    for".
    """
    return mentioned_terms(text, [*extra_vocabulary, *sorted(KNOWN_TECHNOLOGIES)])


__all__ = [
    "ALNUM_TOKEN",
    "ALPHA_WORD",
    "CAMELCASE",
    "KNOWN_TECHNOLOGIES",
    "ORIG_WORD",
    "job_technologies",
    "mentioned_terms",
    "spelling_in",
    "mentions",
    "position_of",
]
