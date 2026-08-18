"""Domain layer: the product's rules, with no infrastructure attached.

Everything here is a pure function or a frozen dataclass over the contracts in
`app.ai.schemas` and the standard library — no SQLAlchemy, no Anthropic SDK, no
Playwright, no FastAPI, no ORM models. That is what makes these rules testable
without a database and reusable from the AI layer, the automation engine and the
API alike.

Import the modules directly (`from app.domain import scoring`). Nothing is
re-exported here on purpose: the domain sits at the bottom of the dependency
graph, and re-exporting would make importing `app.domain.language` drag the AI
schemas in behind it.
"""
