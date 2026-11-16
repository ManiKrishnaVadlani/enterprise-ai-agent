import logging
import os


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    """Configure application logging with a consistent, environment-based level."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(
            f"Invalid LOG_LEVEL {level_name!r}; choose DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )

    logging.basicConfig(level=level, format=LOG_FORMAT)
    # basicConfig intentionally leaves existing handlers alone; set the level
    # explicitly so the application setting still applies under test runners.
    logging.getLogger().setLevel(level)
