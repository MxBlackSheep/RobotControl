"""Primary-only SQL Server behavior, exercised without a live server."""
from datetime import datetime
from unittest.mock import MagicMock

import pyodbc
import pytest
from backend.services import database
from backend.services.database import DatabaseConnectionError, DatabaseService


@pytest.fixture
def sql(monkeypatch):
    connection = MagicMock()
    connect = MagicMock(return_value=connection)
    monkeypatch.setattr(database.pyodbc, "connect", connect)
    service = DatabaseService()
    service._primary_config = {
        "driver": "{ODBC Driver 18 for SQL Server}", "server": "test-server",
        "database": "test-database", "trusted_connection": "yes", "timeout": 3,
    }
    return service, connect, connection, connection.cursor.return_value


def test_service_factory_reuses_instance(monkeypatch):
    monkeypatch.setattr(database, "_service_instance", None)
    assert database.get_database_service() is database.get_database_service()


def test_primary_connection_is_closed(sql):
    service, connect, connection, _ = sql
    with service.get_connection() as opened:
        assert opened is connection
    connect.assert_called_once_with(
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=test-server;"
        "DATABASE=test-database;Trusted_Connection=yes", timeout=3,
    )
    connection.close.assert_called_once()
    assert service.get_pool_stats()["active_mode"] == "primary"


def test_connection_is_closed_when_query_fails(sql):
    service, _, connection, _ = sql
    with pytest.raises(ValueError, match="query failed"):
        with service.get_connection():
            raise ValueError("query failed")
    connection.close.assert_called_once()


def test_connection_failure_has_no_fallback_or_mock_data(sql):
    service, connect, _, _ = sql
    connect.side_effect = pyodbc.Error("server unavailable")
    with pytest.raises(DatabaseConnectionError, match="server unavailable"):
        with service.get_connection():
            pytest.fail("A failed connection must not yield")
    connect.assert_called_once()
    assert service.get_tables() == []
    assert service.perform_health_check() is False
    status = service.get_status()
    assert status.is_connected is False
    assert status.mode == "unavailable"
    assert "server unavailable" in status.error_message


def test_status_reports_primary_database(sql):
    service, _, connection, cursor = sql
    cursor.fetchone.return_value = ("EvoYeast", "HAMILTON")
    status = service.get_status()
    assert status.is_connected is True
    assert status.mode == "primary"
    assert (status.database_name, status.server_name) == ("EvoYeast", "HAMILTON")
    assert status.error_message is None
    connection.close.assert_called_once()


def test_table_metadata(sql, monkeypatch):
    service, _, _, cursor = sql
    cursor.fetchall.return_value = [("Experiments",), ("Plates",)]
    monkeypatch.setattr(service, "_check_table_has_data", lambda name: name == "Experiments")
    assert service.get_tables() == [
        {"name": "Experiments", "has_data": True}, {"name": "Plates", "has_data": False},
    ]


@pytest.mark.parametrize("supports_offset", [True, False])
def test_pagination_filters_and_result_shape(sql, supports_offset):
    service, _, _, cursor = sql
    service._table_columns_cache["experiments"] = ["id", "name", "created"]
    service._supports_offset_fetch = supports_offset
    cursor.description = [("id",), ("name",), ("created",)]
    cursor.fetchall.return_value = [(7, "Sample", datetime(2026, 9, 12, 10, 30))]
    cursor.fetchone.return_value = (12,)
    result = service.get_table_data(
        "Experiments", limit=5, offset=5, order_by="id",
        filters={"name": {"operator": "contains", "value": "Sample"}, "unknown": "ignored"},
    )
    query, params = cursor.execute.call_args_list[0].args
    assert "[name]) LIKE ?" in query
    assert "unknown" not in query
    if supports_offset:
        assert "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" in query
        assert params == ("%Sample%", 5, 5)
    else:
        assert "ROW_NUMBER()" in query
        assert params == ("%Sample%", 6, 10)
    assert result.columns == ["id", "name", "created"]
    assert result.rows == [{"id": 7, "name": "Sample", "created": "2026-09-12T10:30:00"}]
    assert (result.total_count, result.limit, result.offset) == (12, 5, 5)
    assert service.get_performance_stats()["query_count"] == 1


def test_unknown_table_is_rejected(sql):
    service, _, connection, cursor = sql
    cursor.fetchall.return_value = []
    with pytest.raises(ValueError, match="not found"):
        service.get_table_data("Missing")
    connection.close.assert_called_once()


def test_query_parameters_and_dates(sql):
    service, _, connection, cursor = sql
    cursor.description = [("created",)]
    cursor.fetchall.return_value = [(datetime(2026, 9, 12),)]
    cursor.rowcount = 1
    result = service.execute_query("SELECT created FROM Experiments WHERE id = ?", (5,))
    cursor.execute.assert_called_once_with("SELECT created FROM Experiments WHERE id = ?", (5,))
    assert result["rows"] == [{"created": "2026-09-12T00:00:00"}]
    assert result["rowcount"] == 1
    connection.close.assert_called_once()


def test_stored_procedure_commits(sql):
    service, _, connection, cursor = sql
    cursor.description = None
    assert service.execute_stored_procedure("UpdatePlate", {"PlateID": 5})["rows"] == []
    cursor.execute.assert_called_once_with("EXEC [UpdatePlate] @PlateID = ?", (5,))
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()


def test_stored_procedure_rolls_back(sql):
    service, _, connection, cursor = sql
    cursor.execute.side_effect = pyodbc.Error("procedure failed")
    with pytest.raises(pyodbc.Error, match="procedure failed"):
        service.execute_stored_procedure("UpdatePlate", {})
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
