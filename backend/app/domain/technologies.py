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
# is why `c#` and `.net` appear in that shape: `fold` lowercases and strips
# accents but keeps `#` and `.`.
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
        # The .NET half of the industry, which the original list did not cover.
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


@lru_cache(maxsize=4096)
def _term_pattern(folded_term: str) -> re.Pattern[str]:
    r"""Whole-term matcher for an already-folded term.

    A plain `\b` boundary is wrong for this vocabulary: `\bc#\b` never matches,
    because `#` is itself a non-word character and the boundary lands before it
    rather than after; `\b\.net\b` fails on the leading dot for the mirror-image
    reason. Guarding on alphanumeric neighbours instead makes `c#`, `.net` and
    `entity framework` behave like the single terms they are, while still
    refusing to match `net` inside `network`.
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])")


def position_of(haystack: str, term: str) -> int | None:
    """Index of the first whole-term occurrence of `term` in `haystack`, or None."""
    folded = fold(term).strip()
    if not folded:
        return None
    match = _term_pattern(folded).search(fold(haystack))
    return match.start() if match is not None else None


def spans_of(haystack: str, term: str) -> list[tuple[int, int]]:
    """Every whole-term occurrence of `term`, as (start, end) over the folded text."""
    folded = fold(term).strip()
    if not folded:
        return []
    return [match.span() for match in _term_pattern(folded).finditer(fold(haystack))]


def mentions(haystack: str, term: str) -> bool:
    """Whether `haystack` names `term` — the one relevance test used everywhere."""
    return position_of(haystack, term) is not None


def casing_in(haystack: str, term: str) -> str | None:
    """`term` as `haystack` spells it, or None when it does not spell it at all.

    Used to recover a posting's own capitalisation for a term the candidate does
    not list — the dictionary stores `grpc` and `elixir`, while the vacancy the
    user is reading says "gRPC" and "Elixir", and that is the spelling that
    belongs in a gap list shown next to the ad.

    Deliberately searches the *unfolded* text rather than slicing at the folded
    match offset: folding drops combining characters, so an accent earlier in a
    Portuguese description shifts every later index and the slice would come
    back mangled. A term that appears only in accented form simply is not found
    here, and the caller keeps the dictionary spelling.
    """
    folded = fold(term).strip()
    if not folded:
        return None
    match = re.search(
        rf"(?<![A-Za-z0-9]){re.escape(folded)}(?![A-Za-z0-9])", haystack, re.IGNORECASE
    )
    return match.group(0) if match is not None else None


def mentioned_terms(haystack: str, vocabulary: Iterable[str]) -> list[str]:
    """The vocabulary terms `haystack` names, in the order it first names them.

    Casing comes from the vocabulary, not from the haystack: these end up
    rendered in the candidate's own resume, where "PostgreSQL" and "postgresql"
    are not interchangeable. Two spellings of one term collapse to whichever the
    vocabulary offers first, which is why callers put the candidate's own words
    ahead of the dictionary.
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


def job_technologies(text: str, extra_vocabulary: Iterable[str] = ()) -> list[str]:
    """The technologies a posting names, ordered by where it first names them.

    Restricted to the known vocabulary plus whatever the candidate's own resume
    calls a technology (`extra_vocabulary`, which comes first so their spelling
    wins). A posting is mostly prose about benefits and culture, and a purely
    structural scan of it returns the company name and half the boilerplate —
    useful as an invention *flag*, useless as "what this job is asking for".

    Terms wholly subsumed by a longer match are dropped, so a posting asking for
    "ASP.NET Core" yields that and not also the dictionary's bare "asp.net" —
    the same requirement said once, which would otherwise double-count when
    ranking and read as noise in the UI.

    Subsumption is decided per *occurrence*, not by substring: ".NET" is a
    substring of "asp.net core", but a posting titled "Desenvolvedor Backend
    .NET" names .NET somewhere no ASP.NET Core match covers, and dropping the
    headline requirement of the vacancy would be a visible bug. A term is only
    redundant when it appears nowhere outside a longer term's matches.
    """
    own = {fold(term) for term in extra_vocabulary if term.strip()}
    found = [
        # The candidate's own spelling wins for anything they list; for the rest,
        # the posting's own spelling beats the dictionary's folded entry.
        term if fold(term) in own else (casing_in(text, term) or term)
        for term in mentioned_terms(text, [*extra_vocabulary, *sorted(KNOWN_TECHNOLOGIES)])
    ]
    spans = {term: spans_of(text, term) for term in found}
    lengths = {term: len(fold(term)) for term in found}

    def subsumed(term: str) -> bool:
        covers = [
            span
            for other in found
            if other != term and lengths[other] > lengths[term]
            for span in spans[other]
        ]
        if not covers:
            return False
        return all(
            any(start >= outer_start and end <= outer_end for outer_start, outer_end in covers)
            for start, end in spans[term]
        )

    return [term for term in found if not subsumed(term)]


__all__ = [
    "ALNUM_TOKEN",
    "ALPHA_WORD",
    "CAMELCASE",
    "KNOWN_TECHNOLOGIES",
    "ORIG_WORD",
    "casing_in",
    "job_technologies",
    "mentioned_terms",
    "mentions",
    "position_of",
    "spans_of",
]
