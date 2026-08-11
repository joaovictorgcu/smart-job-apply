"""HTTP layer: dependencies, exception handlers and routers.

Intentionally empty of imports: the service layer imports `app.api.errors` to
raise domain exceptions, so importing routers here would create a cycle
(services -> app.api -> routes -> services).
"""
