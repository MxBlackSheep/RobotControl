import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.api.monitoring import get_system_health


def test_sql_health_probe_does_not_block_the_event_loop():
    async def scenario():
        def slow_status():
            time.sleep(.15)
            return SimpleNamespace(is_connected=True, mode="primary", database_name="test", server_name="test", error_message=None)
        db = Mock(get_status=slow_status)
        monitoring = Mock()
        monitoring.websocket_manager.get_connection_stats.return_value = {}
        with patch('backend.api.monitoring.get_database_service', return_value=db), patch('backend.api.monitoring.get_monitoring_service', return_value=monitoring):
            request = asyncio.create_task(get_system_health(current_user={}))
            await asyncio.sleep(.03)
            assert not request.done(), "blocking SQL ran on the API event loop"
            response = json.loads((await request).body)
            assert response['data']['sampled_at']
            assert response['data']['system']['cpu_percent'] >= 0
    asyncio.run(scenario())
