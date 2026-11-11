import asyncio
import json
from unittest.mock import Mock, patch
from backend.api.monitoring import get_system_health


def test_system_health_does_not_read_sql():
    db = Mock()
    with patch("backend.api.monitoring.get_database_service", return_value=db) as get_database:
        response = json.loads(asyncio.run(get_system_health(current_user={})).body)
    get_database.assert_not_called()
    assert response["data"]["sampled_at"]
    assert response["data"]["system"]["cpu_percent"] >= 0
