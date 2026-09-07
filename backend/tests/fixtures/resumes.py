"""A coherent master resume for the tests to derive versions from.

Deliberately not minimal. The behaviour under test is "the same history, told
differently for four different postings", and that needs a history where the
same person genuinely touched .NET, React, Python and API work — in different
jobs, with different achievements, each tagged with what it was actually about.
A two-line fixture could not tell a right answer from a wrong one.

Every technology named here appears in exactly one place it belongs, so a test
can assert both directions: a .NET posting must lead with the .NET job, and a
Python posting must not.
"""

from __future__ import annotations

from typing import Any

MASTER_EXPERIENCES: list[dict[str, Any]] = [
    {
        "key": "globalthings-tech-lead",
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
                "impact": "deploys de 2 semanas para diários",
            },
            {
                "text": "Montou o painel administrativo em Blazor com os times de suporte.",
                "technologies": ["Blazor"],
                "impact": None,
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
        "key": "nexo-fullstack",
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
                "technologies": ["PostgreSQL"],
                "impact": None,
            },
        ],
        "projects": [
            {
                "name": "Design system do checkout",
                "description": "Biblioteca de componentes React usada pelos três produtos.",
                "technologies": ["React", "TypeScript"],
                "outcome": "telas novas em 2 dias em vez de 2 semanas",
            }
        ],
    },
    {
        "key": "datalab-python",
        "company": "DataLab",
        "role": "Engenheiro de Dados",
        "start": "2018-03",
        "end": "2020-05",
        "location": "São Paulo, SP",
        "summary": "Cuidou da ingestão e do tratamento dos dados de telemetria.",
        "technologies": ["Python", "FastAPI", "Airflow", "PostgreSQL"],
        "highlights": [
            {
                "text": "Escreveu os pipelines de ingestão em Python com Airflow.",
                "technologies": ["Python", "Airflow"],
                "impact": "de 4 h para 25 min por carga",
            },
            {
                "text": "Publicou a API interna de consulta em FastAPI.",
                "technologies": ["Python", "FastAPI", "APIs REST"],
                "impact": "usada por 3 times de produto",
            },
        ],
        "projects": [],
    },
]

MASTER_PROJECTS: list[dict[str, Any]] = [
    {
        "name": "sql-lint",
        "description": "Linter de migrações SQL publicado como pacote Python.",
        "technologies": ["Python", "SQL"],
        "outcome": "usado em 4 repositórios internos",
    },
    {
        "name": "dotnet-audit",
        "description": "Analisador de dependências para soluções .NET.",
        "technologies": [".NET 8", "C#"],
        "outcome": "adotado pelo time de plataforma",
    },
]

MASTER_EDUCATION: list[dict[str, Any]] = [
    {
        "institution": "UFPE",
        "degree": "Bacharelado em Ciência da Computação",
        "start": "2014",
        "end": "2018",
        "detail": None,
    }
]

# What a profile carrying the resume above looks like, ready to hand to
# `create_user(profile=...)`.
MASTER_PROFILE: dict[str, Any] = {
    "headline": "Tech Lead — .NET, React e Python",
    "summary": "Nove anos construindo produtos web, do banco ao navegador.",
    "skills": ["Arquitetura de software", "Liderança técnica", "Code review"],
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
        "Airflow",
        "Blazor",
        "Azure DevOps",
    ],
    "experiences": MASTER_EXPERIENCES,
    "projects": MASTER_PROJECTS,
    "education": MASTER_EDUCATION,
    "certifications": ["AZ-204 — Azure Developer Associate"],
}

# Four postings the same person could plausibly answer, each dominated by a
# different part of that history. The descriptions are the only input the
# derivation gets, so they carry the terms a real posting would.
POSTINGS: dict[str, dict[str, str]] = {
    "dotnet": {
        "title": "Desenvolvedor Backend .NET Sênior",
        "description": (
            "Buscamos pessoa sênior em .NET 8 e C# para evoluir nossos serviços de "
            "autorização. Experiência com SQL Server e APIs REST versionadas é "
            "essencial. Azure DevOps no dia a dia."
        ),
    },
    "fullstack": {
        "title": "Engenheiro Full Stack (React)",
        "description": (
            "Time de produto procura alguém forte em React e TypeScript, confortável "
            "em Node.js e PostgreSQL, para tocar o front do checkout e as APIs REST "
            "que o sustentam."
        ),
    },
    "python": {
        "title": "Engenheiro Python",
        "description": (
            "Vaga para trabalhar com Python, FastAPI e Airflow em pipelines de dados. "
            "PostgreSQL no core. Escrever SQL é parte do trabalho."
        ),
    },
    "apis": {
        "title": "Especialista em APIs REST",
        "description": (
            "Procuramos quem já projetou APIs REST em produção, com versionamento e "
            "contrato estável. Node.js ou .NET 8, tanto faz — o que importa é o "
            "desenho da API."
        ),
    },
}
