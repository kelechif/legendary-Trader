"""risk-service: risk_budget, cluster, liquidity, anomaly engines."""

import logging

SERVICE = "risk-service"
log = logging.getLogger(SERVICE)


def run():
    log.info("%s stub ready", SERVICE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
