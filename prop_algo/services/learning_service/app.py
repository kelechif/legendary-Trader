"""learning-service: strategy incubator, research lab, hyper/meta learning."""

from core.logging.logger import get_logger

log = get_logger("learning-service")
SERVICE = "learning-service"


def run():
    log.info("%s stub ready", SERVICE)


if __name__ == "__main__":
    run()
