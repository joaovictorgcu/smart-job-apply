"""Browser-level end-to-end tests.

These are the only tests that launch a real Chromium. They drive the production
Playwright code — `BrowserSession`, `JobSearchPage`, `JobDetailPage`,
`EasyApplyModal` — against the fake portal in `portal.py`, which is served from
inside the browser context and never touches the network.

They are marked `e2e` and excluded from the default run (see `addopts` in
`pyproject.toml`), because they need `playwright install chromium` and take
seconds rather than milliseconds. Run them with `make e2e`.
"""
