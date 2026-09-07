"""A rich, coherent demo candidate and five postings that pull them apart.

This exists because the feature's acceptance criterion is a *demonstration*: one
person, five vacancies, five visibly different resumes. That is impossible to
show — or to test honestly — against a thin fixture, because a candidate with
four skills produces four near-identical derivations no matter how good the
engine is. The differentiation has to be earned by real breadth in the master
resume, and this is that breadth.

Two properties are deliberate and load-bearing.

**Every experience is multi-faceted.** The Globalthings entry is genuinely a
.NET job, a React job, an API job and an architecture job at once, because that
is what a senior position actually looks like. Each of its highlights is tagged
with the technologies it involved, so a .NET posting and a React posting lead
with different sentences from the *same* job without anything being invented —
the sentences were all already there.

**It is internally consistent.** The prose `resume_text` says what the
structured entries say, the periods do not overlap implausibly, the projects use
stacks the experiences also use, and the certifications match the seniority. A
demo dataset that contradicts itself would make the invention guard fire on
truthful output and teach the wrong lesson about the feature.

Used by `scripts/seed_demo.py` and by the test suite, from here, so the two can
never drift apart.
"""

from __future__ import annotations

from typing import Any

# `example.com` rather than a `.test` address: `EmailStr` rejects reserved
# special-use TLDs, and the demo account is registered through the same
# validation the real sign-up uses.
DEMO_EMAIL = "demo@example.com"
DEMO_FULL_NAME = "Alex Moreira"

# The candidate's own spelling of every technology they claim. The derivation
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
# path reads this; the derivation reads the structure. They must agree, or the
# invention guard would flag truthful output from one against the other.
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

# Each highlight carries the technologies it actually involved. That tagging is
# what lets the engine choose between the candidate's own sentences instead of
# guessing at their meaning — and it is why one job reads differently per
# posting without a single word being fabricated.
DEMO_EXPERIENCES: list[dict[str, Any]] = [
    {
        "id": "exp-globalthings",
        "role": "Tech Lead",
        "company": "Globalthings",
        "start": "2023",
        "end": "atual",
        "location": "Recife, PE",
        "summary": (
            "Liderança técnica de uma plataforma interna de gestão de acesso, do "
            "backend à interface."
        ),
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
        ],
        "highlights": [
            {
                "text": (
                    "Desenvolvimento e manutenção de aplicações backend em C# e .NET 8, "
                    "com ASP.NET Core e Entity Framework sobre PostgreSQL."
                ),
                "technologies": [
                    "C#",
                    ".NET",
                    "ASP.NET Core",
                    "Entity Framework",
                    "PostgreSQL",
                ],
            },
            {
                "text": (
                    "Projeto e versionamento de APIs REST consumidas por seis aplicações "
                    "internas, com contratos documentados e compatibilidade preservada "
                    "entre versões."
                ),
                "technologies": ["REST", "APIs"],
            },
            {
                "text": (
                    "Integração das interfaces em React e TypeScript com as APIs de "
                    "backend e o banco de dados."
                ),
                "technologies": ["React", "TypeScript"],
            },
            {
                "text": (
                    "Definição da arquitetura de serviços e do padrão de mensageria com "
                    "RabbitMQ entre os módulos, reduzindo o acoplamento entre times."
                ),
                "technologies": ["Arquitetura de software", "RabbitMQ"],
            },
            {
                "text": (
                    "Condução de code reviews semanais e mentoria de três "
                    "desenvolvedores, com plano de evolução individual."
                ),
                "technologies": ["Liderança técnica", "Code review", "Mentoria"],
            },
            {
                "text": "Publicação dos serviços em Azure com pipelines de deploy automatizados.",
                "technologies": ["Azure", "Docker"],
            },
        ],
    },
    {
        "id": "exp-nexdata",
        "role": "Desenvolvedor backend sênior",
        "company": "Nexdata",
        "start": "2021",
        "end": "2023",
        "location": "Remoto",
        "summary": (
            "Serviços de ingestão e distribuição de dados para clientes do setor "
            "logístico."
        ),
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
        "highlights": [
            {
                "text": (
                    "Desenvolvimento de soluções em Python com FastAPI, integração com "
                    "APIs externas e processamento de dados em lote."
                ),
                "technologies": ["Python", "FastAPI", "APIs"],
            },
            {
                "text": (
                    "Pipelines de ingestão com Celery e PostgreSQL processando quatro "
                    "milhões de registros por dia."
                ),
                "technologies": ["Celery", "PostgreSQL", "Python"],
            },
            {
                "text": (
                    "Padronização das integrações REST com terceiros e cache de "
                    "respostas em Redis, cortando pela metade o tempo de resposta."
                ),
                "technologies": ["REST", "Redis", "APIs"],
            },
            {
                "text": (
                    "Manutenção dos serviços legados em C# e .NET Framework durante a "
                    "migração gradual para Python."
                ),
                "technologies": ["C#", ".NET"],
            },
            {
                "text": (
                    "Containerização dos serviços com Docker e publicação por pipeline "
                    "de integração contínua."
                ),
                "technologies": ["Docker", "Git"],
            },
        ],
    },
    {
        "id": "exp-cofre",
        "role": "Desenvolvedor full stack",
        "company": "Cofre Digital",
        "start": "2019",
        "end": "2021",
        "location": "Recife, PE",
        "summary": "Produtos web de guarda de documentos, da interface ao banco.",
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
        "highlights": [
            {
                "text": (
                    "Desenvolvimento de aplicações web integrando interfaces React com "
                    "APIs de backend e bancos de dados."
                ),
                "technologies": ["React", "JavaScript", "APIs"],
            },
            {
                "text": (
                    "Migração da interface de JavaScript para TypeScript, com uma "
                    "biblioteca de componentes reaproveitada em três produtos."
                ),
                "technologies": ["TypeScript", "React"],
            },
            {
                "text": (
                    "Backend em ASP.NET Core e SQL Server dando suporte à interface, "
                    "com autenticação por token."
                ),
                "technologies": ["ASP.NET Core", "C#", "SQL Server"],
            },
            {
                "text": (
                    "Cobertura de testes de interface com Cypress e de backend com "
                    "xUnit antes de cada release."
                ),
                "technologies": ["Cypress", "xUnit"],
            },
        ],
    },
    {
        "id": "exp-vertex",
        "role": "Desenvolvedor de integrações",
        "company": "Pagamentos Vertex",
        "start": "2017",
        "end": "2019",
        "location": "São Paulo, SP",
        "summary": "Camada de integração entre a plataforma e provedores de pagamento.",
        "technologies": [
            "REST",
            "GraphQL",
            "OAuth2",
            "Python",
            "PostgreSQL",
            "C#",
        ],
        "highlights": [
            {
                "text": (
                    "Construção de APIs REST e GraphQL para parceiros, com autenticação "
                    "OAuth2 e limites de uso por cliente."
                ),
                "technologies": ["REST", "GraphQL", "APIs", "OAuth2"],
            },
            {
                "text": (
                    "Integração com dez provedores de pagamento, normalizando formatos "
                    "divergentes e reconciliando transações diariamente."
                ),
                "technologies": ["APIs", "Python"],
            },
            {
                "text": (
                    "Modelagem e otimização de consultas em PostgreSQL para os "
                    "relatórios financeiros da operação."
                ),
                "technologies": ["PostgreSQL", "SQL"],
            },
        ],
    },
    {
        "id": "exp-tecnosis",
        "role": "Desenvolvedor júnior",
        "company": "Tecnosis",
        "start": "2015",
        "end": "2017",
        "location": "Recife, PE",
        "summary": "Primeiros anos, mantendo o ERP interno da empresa.",
        "technologies": ["C#", "SQL Server", "Python"],
        "highlights": [
            {
                "text": (
                    "Desenvolvimento de rotinas em C# e consultas em SQL Server para o "
                    "ERP da empresa."
                ),
                "technologies": ["C#", "SQL Server", "SQL"],
            },
            {
                "text": "Automação de relatórios recorrentes com Python.",
                "technologies": ["Python"],
            },
        ],
    },
]

DEMO_PROJECTS: list[dict[str, Any]] = [
    {
        "id": "proj-conciliacao",
        "name": "Motor de conciliação financeira",
        "description": (
            "Serviço em Python que reconcilia lançamentos de dez provedores contra o "
            "extrato interno."
        ),
        "outcome": "Divergências caíram de horas de trabalho manual por dia para minutos.",
        "technologies": ["Python", "PostgreSQL", "Celery"],
    },
    {
        "id": "proj-design-system",
        "name": "Design system interno",
        "description": "Biblioteca de componentes React e TypeScript usada por três produtos.",
        "outcome": "Telas novas passaram a sair sem retrabalho de CSS.",
        "technologies": ["React", "TypeScript", "CSS"],
    },
    {
        "id": "proj-gateway",
        "name": "Gateway de APIs de parceiros",
        "description": (
            "Camada em ASP.NET Core que expõe REST e GraphQL sobre os serviços internos."
        ),
        "outcome": "Integração de um novo parceiro passou de semanas para dias.",
        "technologies": ["C#", "ASP.NET Core", "REST", "GraphQL"],
    },
    {
        "id": "proj-kubernetes",
        "name": "Migração para Kubernetes",
        "description": "Migração de nove serviços de máquinas virtuais para Kubernetes no Azure.",
        "outcome": "Deploys deixaram de exigir janela de manutenção.",
        "technologies": ["Kubernetes", "Docker", "Azure"],
    },
    {
        "id": "proj-relatorios",
        "name": "Plataforma de relatórios",
        "description": "Relatórios operacionais em C# sobre SQL Server, com agendamento próprio.",
        "outcome": "Substituiu quinze planilhas mantidas à mão.",
        "technologies": ["C#", "SQL Server", "SQL"],
    },
]

DEMO_EDUCATION: list[dict[str, Any]] = [
    {
        "id": "edu-ufpe",
        "degree": "Bacharelado em Ciência da Computação",
        "institution": "UFPE",
        "start": "2011",
        "end": "2015",
        "detail": "Trabalho final sobre otimização de consultas relacionais.",
    },
    {
        "id": "edu-puc",
        "degree": "Especialização em Arquitetura de Software",
        "institution": "PUC Minas",
        "start": "2019",
        "end": "2020",
        "detail": "",
    },
]

DEMO_CERTIFICATIONS: list[str] = [
    "Microsoft AZ-204 — Developing Solutions for Microsoft Azure",
    "Certified Scrum Foundation",
]


def demo_profile_fields() -> dict[str, Any]:
    """The master resume, as keyword arguments for `Profile` or `ProfileUpdate`."""
    return {
        "headline": DEMO_HEADLINE,
        "location": "Recife, PE",
        "phone": "+55 81 90000-0000",
        "years_of_experience": 10,
        "summary": DEMO_SUMMARY,
        "resume_text": DEMO_RESUME_TEXT,
        "skills": list(DEMO_SKILLS),
        "experiences": [dict(entry) for entry in DEMO_EXPERIENCES],
        "projects": [dict(entry) for entry in DEMO_PROJECTS],
        "education": [dict(entry) for entry in DEMO_EDUCATION],
        "certifications": list(DEMO_CERTIFICATIONS),
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


# Five postings that ask the same candidate for five different things. Each names
# a stack the candidate genuinely has, plus at least one requirement they do not,
# so `unsupported_requirements` has something truthful to report instead of
# always coming back empty.
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
    "DEMO_CERTIFICATIONS",
    "DEMO_EDUCATION",
    "DEMO_EMAIL",
    "DEMO_EXPERIENCES",
    "DEMO_FULL_NAME",
    "DEMO_HEADLINE",
    "DEMO_JOBS",
    "DEMO_PROJECTS",
    "DEMO_RESUME_TEXT",
    "DEMO_SKILLS",
    "DEMO_SUMMARY",
    "demo_profile_fields",
]
