"""Service layer: business rules, always scoped to one user.

Import the modules directly (`from app.services import job_service`). Nothing is
re-exported here on purpose: services import each other, and eager re-exports
would turn those relationships into import cycles.
"""
