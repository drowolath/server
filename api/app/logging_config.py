import structlog


def configure_logging():
    """Configure structlog with JSON rendering and contextvars for request tracing."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # MUST be first — merges per-request context
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
