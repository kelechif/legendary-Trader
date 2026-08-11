"""governance-service: conflicts, stability actions, execution mode rules."""

from core.logging.logger import get_logger

log = get_logger("governance-service")
SERVICE = "governance-service"


def run():
    log.info("%s stub ready", SERVICE)


if __name__ == "__main__":
    run()
