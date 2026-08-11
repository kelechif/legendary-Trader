"""strategy-service: StrategyEngine and signal generation."""

import logging

SERVICE = "strategy-service"
log = logging.getLogger(SERVICE)


def run():
    log.info("%s stub ready", SERVICE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
