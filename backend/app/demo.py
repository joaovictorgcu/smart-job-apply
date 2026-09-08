"""A rich, coherent demo candidate and five postings that pull them apart.

This exists because the feature's acceptance criterion is a *demonstration*: one
person, five vacancies, five visibly different resumes. That is impossible to
show — or to test honestly — against a thin fixture, because a candidate with
four skills produces four near-identical adaptations no matter how good the
engine is. The differentiation has to be earned by real breadth in the master
resume, and this is that breadth.

Shaped for the live model: `DEMO_EXPERIENCES` are `ExperienceCreate` payloads for
the `experiences` table, and `demo_profile_fields()` returns exactly the fields
`ProfileUpdate` accepts. Nothing here is a shape the API would reject — an
earlier version of this file carried profile-level `experiences`/`projects`/
`education`/`certifications` columns that the live schema does not have, and
`ProfileUpdate` silently dropped them, seeding a candidate with no history.

Three properties are deliberate and load-bearing.

**Every experience is multi-faceted.** The Globalthings entry is genuinely a
.NET job, a React job, an API job and an architecture job at once, because that
is what a senior position actually looks like. Its `responsibilities` name their
technologies inside their own sentences, so a .NET posting and a React posting
lead with different sentences from the *same* job without anything being
invented — the sentences were all already there, and `adapt` only reorders them.

**Duties and outcomes are separated.** `responsibilities` is what the candidate
did; `results` is what came of it. The adaptation ranks and reports them
differently, and folding a measurable result into a duty bullet would hide it.

**It is internally consistent.** The prose `resume_text` says what the
structured entries say, the periods do not overlap implausibly, and the projects
use stacks their own experience also lists. A demo dataset that contradicts
itself would make the invention guard fire on truthful output and teach the
wrong lesson about the feature.

Education and certifications live only in `resume_text`: the master resume has
no structured place for them, and inventing one here purely to hold demo data
would put a column in the schema that nothing else needs.

Used by `scripts/seed_demo.py` and by the test suite, from here, so the two can
never drift apart.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# `example.com` rather than a `.test` address: `EmailStr` rejects reserved
# special-use TLDs, and the demo account is registered through the same
# validation the real sign-up uses.
DEMO_EMAIL = "demo@example.com"
DEMO_FULL_NAME = "Alex Moreira"

# The candidate's own spelling of every technology they claim. The adaptation
# prefers these over the dictionary's lower-cased entries, so a resume renders
# "PostgreSQL" and ".NET" the way its owner writes them.
DEMO_SKILLS: list[str] = [
    "C#",
    ".NET",
    "ASP.NET Core",
    "Entity Framework",
    "Python",
    "FastAPI",
    "Django",
    "React",
    "TypeScript",
    "JavaScript",
    "PostgreSQL",
    "SQL Server",
    "Redis",
    "RabbitMQ",
    "Docker",
    "Kubernetes",
    "Azure",
    "REST",
    "GraphQL",
    "OAuth2",
    "Git",
    "xUnit",
    "pytest",
    "Cypress",
    "Arquitetura de software",
    "Liderança técnica",
    "Code review",
    "Mentoria",
]

DEMO_SUMMARY = (
    "Dez anos construindo software de ponta a ponta: backend em C#/.NET e Python, "
    "interfaces em React e TypeScript, e as APIs que ligam os dois. Últimos anos "
    "concentrados em arquitetura de serviços e em conduzir times pequenos."
)

DEMO_HEADLINE = "Desenvolvimento de software — .NET, Python, React e APIs"

# The prose resume, kept consistent with the structured entries below. The AI
# path reads this; the adaptation reads the structure. They must agree, or the
# invention guard would flag truthful output from one against the other. This is
# also the only place the education and certifications live.
DEMO_RESUME_TEXT = """\
Alex Moreira — Desenvolvimento de software (.NET, Python, React, APIs)
Recife, PE · 10 anos de experiência

Resumo
Dez anos construindo software de ponta a ponta: backend em C# e .NET, serviços em
Python, interfaces em React e TypeScript, e as APIs REST e GraphQL que ligam os
dois. Últimos anos concentrados em arquitetura de serviços, mensageria com
RabbitMQ e condução de times pequenos.

Experiência
Tech Lead — Globalthings (2023 — atual)
Backend em C# e .NET 8 com ASP.NET Core e Entity Framework sobre PostgreSQL.
APIs REST versionadas consumidas por seis aplicações internas. Integração das
interfaces em React e TypeScript com o backend. Arquitetura de serviços e
mensageria com RabbitMQ. Code review e mentoria de três desenvolvedores.

Desenvolvedor backend sênior — Nexdata (2021 — 2023)
Soluções em Python com FastAPI, integrações com APIs externas e processamento de
dados. Manutenção de serviços legados em C# durante a migração. Pipelines com
Celery e PostgreSQL. Cache em Redis. Containerização com Docker.

Desenvolvedor full stack — Cofre Digital (2019 — 2021)
Aplicações web integrando React com APIs de backend e bancos de dados. Migração
da interface de JavaScript para TypeScript. Backend em ASP.NET Core e SQL
Server. Testes com Cypress e xUnit.

Desenvolvedor de integrações — Pagamentos Vertex (2017 — 2019)
APIs REST e GraphQL para parceiros, com autenticação OAuth2. Integração com dez
provedores de pagamento. Modelagem e otimização de consultas em PostgreSQL.

Desenvolvedor júnior — Tecnosis (2015 — 2017)
Rotinas em C# e consultas em SQL Server no ERP da empresa. Automação de
relatórios com Python.

Formação
Bacharelado em Ciência da Computação — UFPE (2011 — 2015)
Especialização em Arquitetura de Software — PUC Minas (2019 — 2020)

Certificações
Microsoft AZ-204 — Developing Solutions for Microsoft Azure
Certified Scrum Foundation
"""

# The demo carries years, not months, so each period is anchored to the start of
# its year and the end of the closing one. Precise enough for the only thing
# `adapt` does with dates — ordering equally relevant experiences by recency.
DEMO_EXPERIENCES: list[dict[str, Any]] = [
    {
        "company": "Globalthings",
        "role": "Tech Lead",
        "employment_type": "full_time",
        "location": "Recife, PE",
        "started_on": date(2023, 1, 1),
        "ended_on": None,
        "is_current": True,
        "position": 0,
        "summary": (
            "Liderança técnica de uma plataforma interna de gestão de acesso, do "
            "backend à interface."
        ),
        "responsibilities": [
            (
                "Desenvolvimento e manutenção de aplicações backend em C# e .NET 8, "
                "com ASP.NET Core e Entity Framework sobre PostgreSQL."
            ),
            (
                "Projeto e versionamento de APIs REST consumidas por seis aplicações "
                "internas, com contratos documentados e compatibilidade preservada "
                "entre versões."
            ),
            (
                "Integração das interfaces em React e TypeScript com as APIs de "
                "backend e o banco de dados."
            ),
            (
                "Definição da arquitetura de serviços e do padrão de mensageria com "
                "RabbitMQ entre os módulos."
            ),
            "Condução de code reviews semanais e mentoria de três desenvolvedores.",
            "Publicação dos serviços em Azure com pipelines de deploy automatizados.",
        ],
        "results": [
            "Acoplamento entre times caiu o bastante para que cada um passasse a publicar sozinho.",
            "Três desenvolvedores com plano de evolução individual acompanhado mês a mês.",
        ],
        "technologies": [
            "C#",
            ".NET",
            "ASP.NET Core",
            "Entity Framework",
            "PostgreSQL",
            "React",
            "TypeScript",
            "RabbitMQ",
            "Azure",
            "REST",
            "Arquitetura de software",
            "Liderança técnica",
            "Code review",
            "Mentoria",
        ],
        "projects": [
            {
                "name": "Migração para Kubernetes",
                "description": (
                    "Migração de nove serviços de máquinas virtuais para Kubernetes no Azure."
                ),
                "technologies": ["Kubernetes", "Docker", "Azure"],
            }
        ],
    },
    {
        "company": "Nexdata",
        "role": "Desenvolvedor backend sênior",
        "employment_type": "full_time",
        "location": "Remoto",
        "started_on": date(2021, 1, 1),
        "ended_on": date(2023, 1, 1),
        "is_current": False,
        "position": 1,
        "summary": (
            "Serviços de ingestão e distribuição de dados para clientes do setor logístico."
        ),
        "responsibilities": [
            (
                "Desenvolvimento de soluções em Python com FastAPI, integração com "
                "APIs externas e processamento de dados em lote."
            ),
            "Pipelines de ingestão com Celery e PostgreSQL.",
            "Padronização das integrações REST com terceiros e cache de respostas em Redis.",
            (
                "Manutenção dos serviços legados em C# e .NET Framework durante a "
                "migração gradual para Python."
            ),
            "Containerização dos serviços com Docker e publicação por integração contínua.",
        ],
        "results": [
            "Quatro milhões de registros processados por dia pelos pipelines de ingestão.",
            "Tempo de resposta das integrações cortado pela metade com o cache em Redis.",
        ],
        "technologies": [
            "Python",
            "FastAPI",
            "Celery",
            "PostgreSQL",
            "Redis",
            "Docker",
            "C#",
            ".NET",
            "REST",
        ],
        "projects": [
            {
                "name": "Motor de conciliação financeira",
                "description": (
                    "Serviço em Python que reconcilia lançamentos de dez provedores "
                    "contra o extrato interno."
                ),
                "technologies": ["Python", "PostgreSQL", "Celery"],
            }
        ],
    },
    {
        "company": "Cofre Digital",
        "role": "Desenvolvedor full stack",
        "employment_type": "full_time",
        "location": "Recife, PE",
        "started_on": date(2019, 1, 1),
        "ended_on": date(2021, 1, 1),
        "is_current": False,
        "position": 2,
        "summary": "Produtos web de guarda de documentos, da interface ao banco.",
        "responsibilities": [
            (
                "Desenvolvimento de aplicações web integrando interfaces React com "
                "APIs de backend e bancos de dados."
            ),
            "Migração da interface de JavaScript para TypeScript.",
            (
                "Backend em ASP.NET Core e SQL Server dando suporte à interface, "
                "com autenticação por token."
            ),
            "Cobertura de testes de interface com Cypress e de backend com xUnit.",
        ],
        "results": [
            "Biblioteca de componentes reaproveitada em três produtos depois da migração.",
        ],
        "technologies": [
            "React",
            "TypeScript",
            "JavaScript",
            "ASP.NET Core",
            "C#",
            "SQL Server",
            "Cypress",
            "xUnit",
        ],
        "projects": [
            {
                "name": "Design system interno",
                "description": (
                    "Biblioteca de componentes React e TypeScript usada por três produtos."
                ),
                "technologies": ["React", "TypeScript", "CSS"],
            }
        ],
    },
    {
        "company": "Pagamentos Vertex",
        "role": "Desenvolvedor de integrações",
        "employment_type": "full_time",
        "location": "São Paulo, SP",
        "started_on": date(2017, 1, 1),
        "ended_on": date(2019, 1, 1),
        "is_current": False,
        "position": 3,
        "summary": "Camada de integração entre a plataforma e provedores de pagamento.",
        "responsibilities": [
            (
                "Construção de APIs REST e GraphQL para parceiros, com autenticação "
                "OAuth2 e limites de uso por cliente."
            ),
            (
                "Integração com dez provedores de pagamento, normalizando formatos "
                "divergentes e reconciliando transações diariamente."
            ),
            "Modelagem e otimização de consultas em PostgreSQL para relatórios financeiros.",
        ],
        "results": [
            "Integração de um novo parceiro passou de semanas para dias.",
        ],
        "technologies": ["REST", "GraphQL", "OAuth2", "Python", "PostgreSQL", "C#"],
        "projects": [
            {
                "name": "Gateway de APIs de parceiros",
                "description": (
                    "Camada em ASP.NET Core que expõe REST e GraphQL sobre os "
                    "serviços internos."
                ),
                "technologies": ["C#", "ASP.NET Core", "REST", "GraphQL"],
            }
        ],
    },
    {
        "company": "Tecnosis",
        "role": "Desenvolvedor júnior",
        "employment_type": "full_time",
        "location": "Recife, PE",
        "started_on": date(2015, 1, 1),
        "ended_on": date(2017, 1, 1),
        "is_current": False,
        "position": 4,
        "summary": "Primeiros anos, mantendo o ERP interno da empresa.",
        "responsibilities": [
            "Desenvolvimento de rotinas em C# e consultas em SQL Server para o ERP da empresa.",
            "Automação de relatórios recorrentes com Python.",
        ],
        "results": [
            "Quinze planilhas mantidas à mão substituídas por relatórios agendados.",
        ],
        "technologies": ["C#", "SQL Server", "Python"],
        "projects": [
            {
                "name": "Plataforma de relatórios",
                "description": (
                    "Relatórios operacionais em C# sobre SQL Server, com agendamento próprio."
                ),
                "technologies": ["C#", "SQL Server"],
            }
        ],
    },
]


def demo_profile_fields() -> dict[str, Any]:
    """The unstructured half of the master resume, as `ProfileUpdate` keyword args.

    Only fields `ProfileUpdate` declares. The structured history is separate —
    see `demo_experiences()` — because it lives in its own table and is written
    through `resume_service.create_experience`.
    """
    return {
        "headline": DEMO_HEADLINE,
        "location": "Recife, PE",
        "phone": "+55 81 90000-0000",
        "years_of_experience": 10,
        "summary": DEMO_SUMMARY,
        "resume_text": DEMO_RESUME_TEXT,
        "skills": list(DEMO_SKILLS),
        "preferred_languages": ["pt-BR", "en"],
        "answer_bank": {
            "salary_expectation": "18.000",
            "notice_period": "30 dias",
            "work_authorization": "Sim",
            "years_csharp": "8",
            "years_python": "6",
            "years_react": "5",
        },
    }


def demo_experiences() -> list[dict[str, Any]]:
    """The structured history, as `ExperienceCreate` keyword args, newest first."""
    return [
        {**entry, "projects": [dict(project) for project in entry["projects"]]}
        for entry in DEMO_EXPERIENCES
    ]


# Five postings that ask the same candidate for five different things. Each names
# a stack the candidate genuinely has, plus at least one requirement they do not,
# so `uncovered_requirements` has something truthful to report instead of always
# coming back empty.
DEMO_JOBS: list[dict[str, Any]] = [
    {
        "external_id": "demo-a-backend-dotnet",
        "title": "Desenvolvedor Backend .NET",
        "company": "Vaga A — Meridian Software",
        "location": "Remoto",
        "description": (
            "Buscamos pessoa desenvolvedora backend com forte experiência em C# e "
            ".NET. Você trabalhará em serviços ASP.NET Core com Entity Framework "
            "sobre PostgreSQL, criando e mantendo APIs REST internas.\n\n"
            "Requisitos: C#, .NET 6 ou superior, ASP.NET Core, Entity Framework, "
            "PostgreSQL, testes automatizados com xUnit, Git.\n"
            "Desejável: RabbitMQ, Docker, Azure.\n"
            "Diferencial: experiência prévia com Elixir na camada de streaming."
        ),
    },
    {
        "external_id": "demo-b-fullstack-react",
        "title": "Desenvolvedor Full Stack React",
        "company": "Vaga B — Camada Nove",
        "location": "Híbrido — Recife, PE",
        "description": (
            "Time de produto procurando desenvolvedor full stack com ênfase em "
            "frontend. O dia a dia é construir interfaces em React e TypeScript e "
            "integrá-las às APIs de backend e ao banco de dados.\n\n"
            "Requisitos: React, TypeScript, JavaScript, CSS, consumo de APIs REST, "
            "testes de interface com Cypress.\n"
            "Desejável: ASP.NET Core ou Node no backend, SQL Server, Docker.\n"
            "Diferencial: Svelte para protótipos internos."
        ),
    },
    {
        "external_id": "demo-c-python",
        "title": "Desenvolvedor Python",
        "company": "Vaga C — Dados Vivos",
        "location": "Remoto",
        "description": (
            "Vaga para desenvolvimento de soluções em Python: serviços com FastAPI, "
            "integração com APIs de terceiros e processamento de dados em volume.\n\n"
            "Requisitos: Python, FastAPI ou Django, PostgreSQL, filas com Celery, "
            "Redis, pytest, Docker.\n"
            "Desejável: Kubernetes, observabilidade.\n"
            "Diferencial: Apache Spark para as cargas maiores."
        ),
    },
    {
        "external_id": "demo-d-engenheiro",
        "title": "Engenheiro de Software Sênior",
        "company": "Vaga D — Norte Sistemas",
        "location": "Remoto",
        "description": (
            "Posição sênior com forte componente de arquitetura de software. "
            "Esperamos condução técnica: definir a arquitetura de serviços, "
            "estabelecer padrões de mensageria, conduzir code review e fazer "
            "mentoria do time.\n\n"
            "Requisitos: arquitetura de software, liderança técnica, code review, "
            "mentoria, experiência com mensageria (RabbitMQ ou Kafka), Docker, "
            "Kubernetes, e domínio de pelo menos uma stack entre .NET, Python e "
            "Java.\n"
            "Diferencial: Terraform para provisionamento."
        ),
    },
    {
        "external_id": "demo-e-apis",
        "title": "Desenvolvedor de APIs e Integrações",
        "company": "Vaga E — Ponte Pagamentos",
        "location": "Remoto",
        "description": (
            "Time de integrações contratando para construir e manter APIs REST e "
            "GraphQL destinadas a parceiros externos, com autenticação OAuth2 e "
            "limites de uso por cliente.\n\n"
            "Requisitos: REST, GraphQL, OAuth2, versionamento de contratos, "
            "PostgreSQL, e uma linguagem entre C# e Python.\n"
            "Desejável: Redis para cache de respostas, Docker.\n"
            "Diferencial: gRPC nas integrações internas."
        ),
    },
]


__all__ = [
    "DEMO_EMAIL",
    "DEMO_EXPERIENCES",
    "DEMO_FULL_NAME",
    "DEMO_HEADLINE",
    "DEMO_JOBS",
    "DEMO_RESUME_TEXT",
    "DEMO_SKILLS",
    "DEMO_SUMMARY",
    "demo_experiences",
    "demo_profile_fields",
]
