import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    telegram_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    current_question_index INTEGER NOT NULL DEFAULT 0,
                    answers_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.commit()

    def get_application(self, telegram_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()

        if row is None:
            return None

        application = dict(row)
        application["answers"] = json.loads(application.pop("answers_json") or "{}")
        return application

    def create_or_reset_in_progress(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        full_name: str | None,
    ) -> None:
        now = self._utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO applications (
                    telegram_id,
                    full_name,
                    username,
                    first_name,
                    last_name,
                    created_at,
                    updated_at,
                    status,
                    current_question_index,
                    answers_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress', 0, '{}')
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    completed_at = NULL,
                    status = 'in_progress',
                    current_question_index = 0,
                    answers_json = '{}'
                """,
                (telegram_id, full_name, username, first_name, last_name, now, now),
            )
            connection.commit()

    def save_answer(
        self,
        telegram_id: int,
        question_number: int,
        answer: str,
        next_question_index: int,
    ) -> dict[str, Any] | None:
        application = self.get_application(telegram_id)
        if application is None:
            return None

        answers = application["answers"]
        answers[str(question_number)] = answer

        now = self._utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE applications
                SET answers_json = ?, current_question_index = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (json.dumps(answers, ensure_ascii=False), next_question_index, now, telegram_id),
            )
            connection.commit()

        return self.get_application(telegram_id)

    def mark_completed(self, telegram_id: int, status: str) -> None:
        now = self._utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE applications
                SET status = ?, completed_at = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (status, now, now, telegram_id),
            )
            connection.commit()

    def update_status(self, telegram_id: int, status: str) -> None:
        now = self._utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE applications
                SET status = ?, updated_at = ?
                WHERE telegram_id = ?
                """,
                (status, now, telegram_id),
            )
            connection.commit()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
