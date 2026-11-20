from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from lotto.connectors.db import build_list_games_query
from lotto.connectors.models import GameStatus

from .conftest import GAME_TYPE_ID

DATE_FROM = datetime(2026, 11, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 11, 30, tzinfo=UTC)
LIMIT = 15
OFFSET = 30


def compile_query(query: Select[Any]) -> tuple[str, dict[str, Any]]:
    compiled = query.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split()), compiled.params


def test_list_query_for_scheduled_sorts_ascending() -> None:
    sql, _ = compile_query(
        build_list_games_query(GameStatus.SCHEDULED, None, None, None, LIMIT, OFFSET)
    )

    assert "ORDER BY games.scheduled_at ASC, games.id ASC" in sql


@pytest.mark.parametrize("status", [GameStatus.FINISHED, GameStatus.CANCELLED])
def test_list_query_for_other_statuses_sorts_descending(status: GameStatus) -> None:
    sql, _ = compile_query(
        build_list_games_query(status, None, None, None, LIMIT, OFFSET)
    )

    assert "ORDER BY games.scheduled_at DESC, games.id DESC" in sql


def test_list_query_applies_all_filters_and_pagination() -> None:
    sql, params = compile_query(
        build_list_games_query(
            GameStatus.FINISHED, GAME_TYPE_ID, DATE_FROM, DATE_TO, LIMIT, OFFSET
        )
    )

    assert "games.status = %(status_1)s" in sql
    assert "games.game_type_id = %(game_type_id_1)s::UUID" in sql
    assert "games.scheduled_at >= %(scheduled_at_1)s" in sql
    assert "games.scheduled_at <= %(scheduled_at_2)s" in sql
    assert "LIMIT %(param_1)s::INTEGER OFFSET %(param_2)s::INTEGER" in sql
    assert params["game_type_id_1"] == GAME_TYPE_ID
    assert params["scheduled_at_1"] == DATE_FROM
    assert params["scheduled_at_2"] == DATE_TO
    assert params["param_1"] == LIMIT
    assert params["param_2"] == OFFSET
