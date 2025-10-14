"""
Database Service Unit Tests
Tests for the simplified RobotControl database service layer
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from backend.services.database import DatabaseService
from shared.types import ConnectionMode

class TestDatabaseService:
    """Test suite for DatabaseService"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Clear any existing singleton instances
        DatabaseService._instance = None
        
    def teardown_method(self):
        """Cleanup after each test method"""
        # Reset singleton
        DatabaseService._instance = None
    
    def test_singleton_pattern(self):
        """Test that DatabaseService follows singleton pattern"""
        db1 = DatabaseService()
        db2 = DatabaseService()
        assert db1 is db2, "DatabaseService should be a singleton"
    
    @patch('backend.services.database.pyodbc.connect')
    def test_primary_connection_success(self, mock_connect):
        """Test successful connection to primary database"""
        # Mock successful connection
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        connection = db._get_connection()
        
        assert connection is not None
        assert db.connection_mode == ConnectionMode.PRIMARY
        mock_connect.assert_called_once()
    
    @patch('backend.services.database.pyodbc.connect')
    def test_connection_fallback_to_secondary(self, mock_connect):
        """Test fallback to secondary database when primary fails"""
        # Mock primary connection failure, secondary success
        mock_connection = Mock()
        mock_connect.side_effect = [Exception("Primary connection failed"), mock_connection]
        
        db = DatabaseService()
        connection = db._get_connection()
        
        assert connection is not None
        assert db.connection_mode == ConnectionMode.SECONDARY
        assert mock_connect.call_count == 2
    
    @patch('backend.services.database.pyodbc.connect')
    def test_connection_fallback_to_mock(self, mock_connect):
        """Test fallback to mock data when all database connections fail"""
        # Mock all connections failing
        mock_connect.side_effect = Exception("All connections failed")
        
        db = DatabaseService()
        connection = db._get_connection()
        
        assert connection is None
        assert db.connection_mode == ConnectionMode.MOCK
        assert mock_connect.call_count == 2  # Tried both primary and secondary
    
    @patch('backend.services.database.pyodbc.connect')
    def test_get_tables_with_connection(self, mock_connect):
        """Test getting tables list with active database connection"""
        # Mock successful connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ('Experiments', 'dbo', 100),
            ('Plates', 'dbo', 50),
            ('Users', 'dbo', 5)
        ]
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        tables = db.get_tables()
        
        assert len(tables) == 3
        assert tables[0]['name'] == 'Experiments'
        assert tables[0]['row_count'] == 100
        assert tables[1]['name'] == 'Plates'
        mock_cursor.execute.assert_called_once()
    
    @patch('backend.services.database.pyodbc.connect')
    def test_get_tables_with_mock_data(self, mock_connect):
        """Test getting tables list with mock data when no connection"""
        # Mock connection failure to trigger mock mode
        mock_connect.side_effect = Exception("No connection")
        
        db = DatabaseService()
        tables = db.get_tables()
        
        # Should return mock tables
        assert len(tables) > 0
        assert db.connection_mode == ConnectionMode.MOCK
        table_names = [table['name'] for table in tables]
        assert 'Experiments' in table_names
    
    @patch('backend.services.database.pyodbc.connect')
    def test_get_table_data_with_connection(self, mock_connect):
        """Test getting table data with active database connection"""
        # Mock successful connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.description = [('id',), ('name',), ('status',)]
        mock_cursor.fetchall.return_value = [
            (1, 'Test Experiment 1', 'completed'),
            (2, 'Test Experiment 2', 'running')
        ]
        mock_cursor.rowcount = 2
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        result = db.get_table_data('Experiments', page=1, limit=10)
        
        assert result['total_rows'] == 2
        assert len(result['data']) == 2
        assert result['columns'] == ['id', 'name', 'status']
        assert result['page'] == 1
        mock_cursor.execute.assert_called()
    
    @patch('backend.services.database.pyodbc.connect')
    def test_get_table_data_with_mock_data(self, mock_connect):
        """Test getting table data with mock data when no connection"""
        # Mock connection failure
        mock_connect.side_effect = Exception("No connection")
        
        db = DatabaseService()
        result = db.get_table_data('Experiments', page=1, limit=5)
        
        # Should return mock data
        assert result['total_rows'] > 0
        assert len(result['data']) > 0
        assert len(result['columns']) > 0
        assert result['page'] == 1
    
    @patch('backend.services.database.pyodbc.connect')
    def test_execute_query_with_connection(self, mock_connect):
        """Test executing custom query with active database connection"""
        # Mock successful connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.description = [('count',)]
        mock_cursor.fetchall.return_value = [(42,)]
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        result = db.execute_query("SELECT COUNT(*) as count FROM Experiments")
        
        assert result['success'] is True
        assert result['data'] == [(42,)]
        assert result['columns'] == ['count']
        mock_cursor.execute.assert_called_with("SELECT COUNT(*) as count FROM Experiments")
    
    @patch('backend.services.database.pyodbc.connect')
    def test_execute_query_error_handling(self, mock_connect):
        """Test query execution error handling"""
        # Mock connection with query error
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("SQL syntax error")
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        result = db.execute_query("INVALID SQL")
        
        assert result['success'] is False
        assert 'error' in result
        assert 'SQL syntax error' in result['error']
    
    @patch('backend.services.database.pyodbc.connect')
    def test_connection_pooling(self, mock_connect):
        """Test that connection pooling reuses connections"""
        # Mock successful connection
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        
        # Get multiple connections
        conn1 = db._get_connection()
        conn2 = db._get_connection()
        
        # Should reuse the same connection
        assert conn1 is conn2
        # Should only create connection once
        mock_connect.assert_called_once()
    
    @patch('backend.services.database.pyodbc.connect')
    def test_connection_health_check(self, mock_connect):
        """Test connection health check functionality"""
        # Mock successful connection
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        is_healthy = db.check_connection_health()
        
        assert is_healthy is True
        mock_cursor.execute.assert_called_with("SELECT 1")
    
    @patch('backend.services.database.pyodbc.connect')
    def test_connection_health_check_failure(self, mock_connect):
        """Test connection health check when connection fails"""
        # Mock connection failure
        mock_connect.side_effect = Exception("Connection failed")
        
        db = DatabaseService()
        is_healthy = db.check_connection_health()
        
        assert is_healthy is False
    
    def test_mock_data_tables_structure(self):
        """Test that mock data has proper structure"""
        # Force mock mode
        with patch('backend.services.database.pyodbc.connect', side_effect=Exception("No DB")):
            db = DatabaseService()
            tables = db.get_tables()
            
            assert len(tables) > 0
            for table in tables:
                assert 'name' in table
                assert 'schema' in table
                assert 'row_count' in table
                assert isinstance(table['row_count'], int)
    
    def test_mock_data_experiments_table(self):
        """Test mock data for Experiments table"""
        # Force mock mode
        with patch('backend.services.database.pyodbc.connect', side_effect=Exception("No DB")):
            db = DatabaseService()
            result = db.get_table_data('Experiments', page=1, limit=10)
            
            assert result['total_rows'] > 0
            assert len(result['data']) > 0
            assert 'columns' in result
            assert len(result['columns']) > 0
            # Should have typical experiment columns
            expected_columns = ['id', 'method_name', 'start_time', 'status']
            for col in expected_columns:
                assert col in [c.lower() for c in result['columns']]


class TestDatabaseServicePerformance:
    """Performance tests for DatabaseService"""
    
    @patch('backend.services.database.pyodbc.connect')
    def test_large_table_pagination(self, mock_connect):
        """Test pagination with large datasets"""
        # Mock large dataset
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.description = [('id',), ('name',)]
        
        # Simulate large table with 1000 rows
        large_dataset = [(i, f'Item {i}') for i in range(1, 101)]  # First page of 100
        mock_cursor.fetchall.return_value = large_dataset
        mock_cursor.rowcount = 100
        mock_connect.return_value = mock_connection
        
        db = DatabaseService()
        result = db.get_table_data('LargeTable', page=1, limit=100)
        
        assert len(result['data']) == 100
        assert result['page'] == 1
        assert result['columns'] == ['id', 'name']
    
    @patch('backend.services.database.pyodbc.connect')
    def test_connection_timeout_handling(self, mock_connect):
        """Test handling of connection timeouts"""
        # Mock timeout exception
        mock_connect.side_effect = Exception("Timeout occurred")
        
        db = DatabaseService()
        # Should gracefully fall back to mock data
        tables = db.get_tables()
        
        assert len(tables) > 0  # Mock data should be returned
        assert db.connection_mode == ConnectionMode.MOCK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])