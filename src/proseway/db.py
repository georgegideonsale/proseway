"""SQLite storage. One file, WAL mode, safe to use from the server and the converter process."""

from __future__ import annotations

import contextlib
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS books (
  id TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  author TEXT NOT NULL DEFAULT '',
  file_name TEXT NOT NULL DEFAULT '',
  file_size INTEGER NOT NULL DEFAULT 0,
  page_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',   -- queued | converting | paused | ready | error | cancelled
  error TEXT,
  pipeline_version INTEGER NOT NULL DEFAULT 0,
  pages_done INTEGER NOT NULL DEFAULT 0,
  word_count INTEGER NOT NULL DEFAULT 0,
  has_cover INTEGER NOT NULL DEFAULT 0,
  toc_json TEXT NOT NULL DEFAULT '[]',
  stats_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  last_opened_at REAL
);

CREATE TABLE IF NOT EXISTS blocks (
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  id TEXT NOT NULL,
  chapter INTEGER NOT NULL,
  type TEXT NOT NULL,
  page INTEGER NOT NULL,
  level INTEGER NOT NULL DEFAULT 0,
  text TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (book_id, seq)
);
CREATE INDEX IF NOT EXISTS blocks_by_id ON blocks(book_id, id);
CREATE INDEX IF NOT EXISTS blocks_by_chapter ON blocks(book_id, chapter, seq);

CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
  text, book_id UNINDEXED, block_id UNINDEXED, tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS annotations (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                      -- highlight | bookmark
  color TEXT,
  group_id TEXT,
  block_id TEXT NOT NULL,
  start INTEGER NOT NULL DEFAULT 0,
  end INTEGER NOT NULL DEFAULT 0,
  exact TEXT NOT NULL DEFAULT '',
  prefix TEXT NOT NULL DEFAULT '',
  suffix TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  page INTEGER,
  seq INTEGER,
  orphaned INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS annotations_by_book ON annotations(book_id, seq);

CREATE TABLE IF NOT EXISTS positions (
  book_id TEXT PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
  block_id TEXT NOT NULL,
  seq INTEGER NOT NULL DEFAULT 0,
  progress REAL NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  created_at REAL NOT NULL,
  last_seen REAL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def init(self) -> Database:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        return self

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")


def now() -> float:
    return time.time()
