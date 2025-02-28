import os
import psycopg2
import logging
from flask import g

logger = logging.getLogger(__name__)


def get_db():

    if "db" not in g:
        # slogger.info("No existing database connection found. Creating a new one.")
        g.db = connect_db()

    return g.db


def connect_db():

    try:
        logger.info("Attempting to connect to the PostgreSQL database.")
        if os.environ.get("FLASK_ENV", "development") == "development":
            conn = psycopg2.connect(os.environ.get("DATABASE_PUBLIC_URL"))
        else:
            conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
        logger.info("Successfully created a new DB connection.")
        return conn
    except Exception as e:
        logger.error("Failed to create a DB connection: %s", e)
        raise e


def close_db():

    db = g.pop("db", None)
    if db is not None:
        # logger.info("Closed the database connection.")
        db.close()
