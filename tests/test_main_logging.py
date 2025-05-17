import logging
from argparse import Namespace

import mcp_search_hub.main as main_mod


def test_main_configures_logging(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    args = Namespace(
        transport=None,
        host=None,
        port=None,
        log_level="WARNING",
        linkup_api_key=None,
        exa_api_key=None,
        perplexity_api_key=None,
        tavily_api_key=None,
        firecrawl_api_key=None,
    )

    monkeypatch.setattr(main_mod, "parse_args", lambda: args)

    logged_levels = []

    def dummy_init(self):
        pass

    def dummy_run(self, transport, host, port, log_level):
        logger = logging.getLogger("mcp_search_hub")
        logged_levels.append(logger.getEffectiveLevel())
        logger.debug("debug message")
        logger.warning("warning message")

    monkeypatch.setattr(main_mod.SearchServer, "__init__", dummy_init)
    monkeypatch.setattr(main_mod.SearchServer, "run", dummy_run)

    monkeypatch.delenv("LOG_LEVEL", raising=False)
    main_mod.get_settings.cache_clear()
    main_mod.main()

    assert logged_levels == [logging.WARNING]
    messages = [rec.message for rec in caplog.records]
    assert "warning message" in messages
    assert "debug message" not in messages
