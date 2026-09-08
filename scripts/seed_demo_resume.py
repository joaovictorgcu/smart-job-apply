#!/usr/bin/env python3
"""Seed one account with a real master resume and four applications from it.

This exists to make the per-application resume *visible* in a running app in
one command, without a LinkedIn session, an API key or a browser:

    python scripts/seed_demo_resume.py --email you@example.com

It fills the account's master resume with a coherent history (three positions,
each with achievements tagged by technology), creates four postings — Backend
.NET, Full Stack React, Python and APIs — and derives each application's own
version of the resume. Open the four applications side by side and the same
history leads with a different job, a different first achievement and a
different summary in each.

Nothing here talks to LinkedIn and nothing is submitted: the applications are
created as drafts, exactly as the review flow expects them.

Idempotent per posting: running it twice reuses the same jobs (they are
deduplicated by external id) and re-derives their versions.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.database.session import dispose_engine, init_models, session_scope  # noqa: E402
from app.models import Application, ApplicationStatus, Job, JobStatus, User  # noqa: E402
from app.observability import configure_logging  # noqa: E402
from app.services import resume_service, user_service  # noqa: E402

# --------------------------------------------------------------------------- #
# The master resume
# --------------------------------------------------------------------------- #
#
# Coherent on purpose: the periods do not overlap, every technology sits in the
# job where it was actually used, and each achievement carries the tags that let
# one posting open a position with it and another posting bury it. A vaguer
# fixture would make the demo prove nothing.

EXPERIENCES: list[dict[str, Any]] = [
    {
        "company": "Globalthings",
        "role": "Tech Lead",
        "start": "2023-02",
        "end": None,
        "location": "Recife, PE",
        "summary": "Lidera a plataforma de gestão de acessos usada por 40 clientes.",
        "technologies": [".NET 8", "C#", "SQL Server", "Azure DevOps", "Blazor"],
        "highlights": [
            {
                "text": "Reescreveu o serviço de autorização em .NET 8 com APIs REST versionadas.",
                "technologies": [".NET 8", "C#", "APIs REST"],
                "impact": "p95 de 420 ms para 120 ms",
            },
            {
                "text": "Padronizou o pipeline de release no Azure DevOps.",
                "technologies": ["Azure DevOps"],
                "impact": "deploys de duas semanas para diários",
            },
            {
                "text": "Montou o painel administrativo em Blazor junto com o suporte.",
                "technologies": ["Blazor", "C#"],
                "impact": "40% menos chamados de configuração",
            },
        ],
        "projects": [
            {
                "name": "Gateway de autorização",
                "description": "Serviço central de permissões consumido por seis produtos.",
                "technologies": [".NET 8", "APIs REST", "SQL Server"],
                "outcome": "seis integrações migradas sem downtime",
            }
        ],
    },
    {
        "company": "Nexo Digital",
        "role": "Engenheiro Full Stack",
        "start": "2020-06",
        "end": "2023-01",
        "location": "Remoto",
        "summary": "Construiu o produto de checkout de ponta a ponta com um time de cinco.",
        "technologies": ["React", "TypeScript", "Node.js", "PostgreSQL", "APIs REST"],
        "highlights": [
            {
                "text": "Refez o checkout em React e TypeScript com testes de componente.",
                "technologies": ["React", "TypeScript"],
                "impact": "conversão de 61% para 74%",
            },
            {
                "text": "Expôs as APIs REST de pagamento em Node.js.",
                "technologies": ["Node.js", "APIs REST"],
                "impact": "1,2 mil requisições por minuto no pico",
            },
            {
                "text": "Modelou o histórico de pedidos em PostgreSQL.",
                "technologies": ["PostgreSQL", "SQL"],
                "impact": "consultas de 3 s para 180 ms",
            },
        ],
        "projects": [
            {
                "name": "Design system do checkout",
                "description": "Biblioteca de componentes React usada pelos três produtos.",
                "technologies": ["React", "TypeScript"],
                "outcome": "telas novas em dois dias em vez de duas semanas",
            }
        ],
    },
    {
        "company": "DataLab",
        "role": "Engenheiro de Dados",
        "start": "2018-03",
        "end": "2020-05",
        "location": "São Paulo, SP",
        "summary": "Cuidou da ingestão e do tratamento dos dados de telemetria.",
        "technologies": ["Python", "FastAPI", "Airflow", "PostgreSQL"],
        "highlights": [
            {
                "text": "Escreveu os pipelines de ingestão em Python orquestrados por Airflow.",
                "technologies": ["Python", "Airflow"],
                "impact": "de 4 h para 25 min por carga",
            },
            {
                "text": "Publicou a API interna de consulta em FastAPI.",
                "technologies": ["Python", "FastAPI", "APIs REST"],
                "impact": "usada por três times de produto",
            },
            {
                "text": "Automatizou a validação de schemas em SQL.",
                "technologies": ["SQL", "PostgreSQL"],
                "impact": "zero incidentes de carga em 8 meses",
            },
        ],
        "projects": [],
    },
]

PROFILE: dict[str, Any] = {
    "headline": "Tech Lead — .NET, React e Python",
    "summary": "Nove anos construindo produtos web, do banco de dados ao navegador.",
    "skills": ["Arquitetura de software", "Liderança técnica", "Code review", "Mentoria"],
    "technologies": [
        ".NET 8",
        "C#",
        "React",
        "TypeScript",
        "Node.js",
        "Python",
        "FastAPI",
        "APIs REST",
        "PostgreSQL",
        "SQL Server",
        "SQL",
        "Airflow",
        "Blazor",
        "Azure DevOps",
    ],
    "experiences": EXPERIENCES,
    "projects": [
        {
            "name": "sql-lint",
            "description": "Linter de migrações SQL publicado como pacote Python.",
            "technologies": ["Python", "SQL"],
            "outcome": "usado em quatro repositórios internos",
        },
        {
            "name": "dotnet-audit",
            "description": "Analisador de dependências para soluções .NET.",
            "technologies": [".NET 8", "C#"],
            "outcome": "adotado pelo time de plataforma",
        },
    ],
    "education": [
        {
            "institution": "UFPE",
            "degree": "Bacharelado em Ciência da Computação",
            "start": "2014",
            "end": "2018",
        }
    ],
    "certifications": ["AZ-204 — Azure Developer Associate"],
}

# Four postings the same person could answer, each dominated by a different part
# of that history. `external_id` keeps re-running the script idempotent.
POSTINGS: list[dict[str, Any]] = [
    {
        "external_id": "demo-dotnet",
        "title": "Desenvolvedor Backend .NET Sênior",
        "company": "Contoso Serviços",
        "description": (
            "Buscamos pessoa sênior em .NET 8 e C# para evoluir nossos serviços de "
            "autorização. Experiência com SQL Server e APIs REST versionadas é "
            "essencial. Azure DevOps no dia a dia."
        ),
    },
    {
        "external_id": "demo-fullstack",
        "title": "Engenheiro Full Stack (React)",
        "company": "Loja Verde",
        "description": (
            "Time de produto procura alguém forte em React e TypeScript, confortável "
            "em Node.js e PostgreSQL, para tocar o front do checkout e as APIs REST "
            "que o sustentam."
        ),
    },
    {
        "external_id": "demo-python",
        "title": "Engenheiro Python",
        "company": "Telemetria BR",
        "description": (
            "Vaga para trabalhar com Python, FastAPI e Airflow em pipelines de dados. "
            "PostgreSQL no core e escrever SQL é parte do trabalho."
        ),
    },
    {
        "external_id": "demo-apis",
        "title": "Especialista em APIs REST",
        "company": "Integra Pay",
        "description": (
            "Procuramos quem já projetou APIs REST em produção, com versionamento e "
            "contrato estável. Node.js ou .NET 8, tanto faz — o que importa é o "
            "desenho da API."
        ),
    },
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="seed_demo_resume.py",
        description="Fill an account's master resume and derive four applications from it.",
    )
    parser.add_argument("--email", required=True, help="E-mail of an existing account.")
    return parser.parse_args(argv)


async def seed(email: str) -> None:
    await init_models()
    try:
        async with session_scope() as session:
            user = (
                await session.execute(select(User).where(User.email == email.strip().lower()))
            ).scalar_one_or_none()
            if user is None:
                raise SystemExit(
                    f"No account with e-mail {email}. Create one first: "
                    "python scripts/create_user.py"
                )

            profile = await user_service.get_or_create_profile(session, user)
            for field, value in PROFILE.items():
                setattr(profile, field, value)
            await session.flush()
            # Round-trip through the document so the stored experience keys are
            # the canonical ones the API would have assigned.
            profile.experiences = [
                experience.model_dump(mode="json")
                for experience in user_service.master_document(profile).experiences
            ]
            await session.flush()

            summaries: list[tuple[str, str, list[str]]] = []
            for posting in POSTINGS:
                job = (
                    await session.execute(
                        select(Job).where(
                            Job.user_id == user.id, Job.external_id == posting["external_id"]
                        )
                    )
                ).scalar_one_or_none()
                if job is None:
                    job = Job(
                        user_id=user.id,
                        external_id=posting["external_id"],
                        source="linkedin",
                        title=posting["title"],
                        company=posting["company"],
                        location="Remoto",
                        description=posting["description"],
                        workplace_type="remote",
                        easy_apply=True,
                        detected_language="pt",
                        status=JobStatus.ANALYZED,
                    )
                    session.add(job)
                    await session.flush()

                application = (
                    await session.execute(select(Application).where(Application.job_id == job.id))
                ).scalar_one_or_none()
                if application is None:
                    application = Application(
                        user_id=user.id,
                        job_id=job.id,
                        status=ApplicationStatus.DRAFT,
                        screening_answers=[],
                    )
                    session.add(application)
                    await session.flush()

                _, row = await resume_service.derive_version(session, user, application.id)
                leading = row.document["experiences"][0]
                summaries.append(
                    (
                        job.title,
                        f"{leading['role']} — {leading['company']}",
                        list(row.focus)[:3],
                    )
                )
    finally:
        await dispose_engine()

    print(f"Master resume filled for {email}: {len(EXPERIENCES)} experiences.")
    print(f"{len(summaries)} applications, each with its own version of it:\n")
    for title, leading, focus in summaries:
        print(f"  {title}")
        print(f"    abre com: {leading}")
        print(f"    prioriza: {', '.join(focus) if focus else '(nenhuma interseção)'}\n")
    print("Open Candidaturas in the app: the 'Currículo' column shows each one's emphasis.")


def main(argv: list[str] | None = None) -> int:
    configure_logging(level="WARNING")
    args = parse_args(argv)
    try:
        asyncio.run(seed(args.email))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, do not traceback
        print(f"Could not seed the demo resume: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
