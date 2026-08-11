"""market-data-service: broker adapters and market history."""

import logging

SERVICE = "market-data-service"
log = logging.getLogger(SERVICE)


def run():
    log.info("%s stub ready", SERVICE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
