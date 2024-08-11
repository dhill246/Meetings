import logging
from logging.handlers import RotatingFileHandler

def configure_logging(app):
    # Set log level
    app.logger.setLevel(logging.INFO)

    # Create a file handler which logs even debug messages
    fh = RotatingFileHandler('app.log', maxBytes=10000000, backupCount=5)
    fh.setLevel(logging.INFO)

    # Create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Add handlers to the logger
    app.logger.addHandler(fh)
    app.logger.addHandler(ch)

    # Attach to Flask's logger for app wide use
    logging.getLogger().addHandler(fh)
    logging.getLogger().addHandler(ch)