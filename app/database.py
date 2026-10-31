"""SQLAlchemy database engine and compatibility cursor for the legacy routes.

The compatibility layer lets the existing MySQL SQL remain stable while the
application moves from mysql.connector to SQLAlchemy. New code should prefer
SessionLocal/get_db and SQLAlchemy ORM models.
"""
from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Result
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()


def _database_url():
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    return URL.create(
        "mysql+mysqlconnector",
        username=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "lbvd"),
        query={"charset": "utf8mb4"},
    )


engine = create_engine(
    _database_url(),
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency for routes that use SQLAlchemy ORM sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SQLAlchemyCursor:
    """Small adapter preserving the cursor interface used by older routes."""
    def __init__(self, connection: "SQLAlchemyConnection", dictionary: bool = False):
        self.connection = connection
        self.dictionary = dictionary
        self.result: Result | None = None
        self.lastrowid = None
        self.rowcount = -1

    @staticmethod
    def _statement(sql: str, params: Any):
        # Existing routes use MySQL connector's %s positional placeholders.
        if isinstance(params, dict):
            return text(sql), params
        values = tuple(params or ())
        names = iter(range(len(values)))
        converted = re.sub(r"%s", lambda _m: f":p{next(names)}", sql)
        return text(converted), {f"p{i}": value for i, value in enumerate(values)}

    def execute(self, sql: str, params: Any = None):
        statement, bound = self._statement(sql, params)
        self.result = self.connection.raw.execute(statement, bound)
        self.rowcount = self.result.rowcount
        try:
            self.lastrowid = self.result.lastrowid
        except Exception:
            self.lastrowid = None
        return self

    def _convert(self, row):
        if row is None:
            return None
        if self.dictionary:
            return dict(row._mapping)
        return tuple(row)

    def fetchone(self):
        return self._convert(self.result.fetchone()) if self.result is not None else None

    def fetchall(self):
        return [self._convert(row) for row in self.result.fetchall()] if self.result is not None else []

    def close(self):
        if self.result is not None:
            self.result.close()
            self.result = None


class SQLAlchemyConnection:
    """Connection facade with the small subset of the old connector API used."""
    def __init__(self, raw: Connection):
        self.raw = raw

    def cursor(self, dictionary: bool = False):
        return SQLAlchemyCursor(self, dictionary=dictionary)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def start_transaction(self):
        if not self.raw.in_transaction():
            self.raw.begin()

    def close(self):
        self.raw.close()


def get_db_connection() -> SQLAlchemyConnection:
    """Legacy-route entry point backed by SQLAlchemy, not mysql.connector."""
    return SQLAlchemyConnection(engine.connect())
