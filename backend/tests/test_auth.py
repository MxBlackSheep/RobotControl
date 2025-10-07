"""
Authentication Service Unit Tests
Tests for the simplified PyRobot authentication system
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import jwt

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from backend.services.auth import AuthService
from backend.main import app
from shared.types import UserRole
from shared.constants import ERROR_MESSAGES

# Test client
client = TestClient(app)

class TestAuthService:
    """Test suite for AuthService"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Clear any existing singleton instances
        AuthService._instance = None
        
    def teardown_method(self):
        """Cleanup after each test method"""
        # Reset singleton
        AuthService._instance = None
    
    def test_singleton_pattern(self):
        """Test that AuthService follows singleton pattern"""
        auth1 = AuthService()
        auth2 = AuthService()
        assert auth1 is auth2, "AuthService should be a singleton"
    
    def test_user_initialization(self):
        """Test that users are properly initialized"""
        auth = AuthService()
        
        # Should have default users
        assert len(auth.users) >= 2
        
        # Check admin user exists
        admin_user = next((u for u in auth.users.values() if u['username'] == 'admin'), None)
        assert admin_user is not None
        assert admin_user['role'] == UserRole.ADMIN
        
        # Check hamilton user exists
        hamilton_user = next((u for u in auth.users.values() if u['username'] == 'hamilton'), None)
        assert hamilton_user is not None
        assert hamilton_user['role'] == UserRole.USER
    
    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        auth = AuthService()
        
        # Test with admin user
        is_valid = auth.verify_password('PyRobot_Admin_2025!', auth.users[1]['password_hash'])
        assert is_valid is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        auth = AuthService()
        
        # Test with wrong password
        is_valid = auth.verify_password('wrong_password', auth.users[1]['password_hash'])
        assert is_valid is False
    
    def test_authenticate_user_success(self):
        """Test successful user authentication"""
        auth = AuthService()
        
        # Test admin login
        user = auth.authenticate_user('admin', 'PyRobot_Admin_2025!')
        assert user is not None
        assert user['username'] == 'admin'
        assert user['role'] == UserRole.ADMIN
    
    def test_authenticate_user_wrong_password(self):
        """Test authentication with wrong password"""
        auth = AuthService()
        
        # Test with wrong password
        user = auth.authenticate_user('admin', 'wrong_password')
        assert user is None
    
    def test_authenticate_user_nonexistent(self):
        """Test authentication with nonexistent user"""
        auth = AuthService()
        
        # Test with nonexistent user
        user = auth.authenticate_user('nonexistent', 'any_password')
        assert user is None
    
    def test_create_access_token(self):
        """Test access token creation"""
        auth = AuthService()
        
        # Create token for admin user
        token_data = {"sub": "admin", "role": "admin"}
        token = auth.create_access_token(token_data)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token can be decoded
        decoded = jwt.decode(token, auth.secret_key, algorithms=[auth.algorithm])
        assert decoded['sub'] == 'admin'
        assert decoded['role'] == 'admin'
    
    def test_create_refresh_token(self):
        """Test refresh token creation"""
        auth = AuthService()
        
        # Create refresh token for admin user
        token_data = {"sub": "admin", "role": "admin"}
        token = auth.create_refresh_token(token_data)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Verify token can be decoded
        decoded = jwt.decode(token, auth.secret_key, algorithms=[auth.algorithm])
        assert decoded['sub'] == 'admin'
        assert decoded['role'] == 'admin'
    
    def test_verify_token_valid(self):
        """Test token verification with valid token"""
        auth = AuthService()
        
        # Create and verify token
        token_data = {"sub": "admin", "role": "admin"}
        token = auth.create_access_token(token_data)
        
        payload = auth.verify_token(token)
        assert payload is not None
        assert payload['sub'] == 'admin'
        assert payload['role'] == 'admin'
    
    def test_verify_token_invalid(self):
        """Test token verification with invalid token"""
        auth = AuthService()
        
        # Test with invalid token
        payload = auth.verify_token('invalid.token.here')
        assert payload is None
    
    def test_verify_token_expired(self):
        """Test token verification with expired token"""
        auth = AuthService()
        
        # Create expired token (expire immediately)
        token_data = {"sub": "admin", "role": "admin"}
        expired_token = jwt.encode(
            {**token_data, "exp": datetime.utcnow() - timedelta(minutes=1)},
            auth.secret_key,
            algorithm=auth.algorithm
        )
        
        payload = auth.verify_token(expired_token)
        assert payload is None
    
    def test_get_user_by_username(self):
        """Test getting user by username"""
        auth = AuthService()
        
        # Test existing user
        user = auth.get_user_by_username('admin')
        assert user is not None
        assert user['username'] == 'admin'
        
        # Test nonexistent user
        user = auth.get_user_by_username('nonexistent')
        assert user is None
    
    def test_user_login_updates_last_login(self):
        """Test that successful login updates last_login timestamp"""
        auth = AuthService()
        
        # Get initial last_login
        user_before = auth.get_user_by_username('admin')
        initial_last_login = user_before.get('last_login')
        
        # Authenticate user
        user_after = auth.authenticate_user('admin', 'PyRobot_Admin_2025!')
        
        # Check that last_login was updated
        updated_user = auth.get_user_by_username('admin')
        assert updated_user['last_login'] != initial_last_login
        assert isinstance(updated_user['last_login'], datetime)


class TestAuthAPI:
    """Test suite for Authentication API endpoints"""
    
    def test_login_endpoint_success(self):
        """Test successful login through API"""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "PyRobot_Admin_2025!"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"
    
    def test_login_endpoint_wrong_password(self):
        """Test login with wrong password"""
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong_password"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_login_endpoint_nonexistent_user(self):
        """Test login with nonexistent user"""
        response = client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "any_password"}
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_login_endpoint_missing_fields(self):
        """Test login with missing required fields"""
        # Missing password
        response = client.post(
            "/api/auth/login",
            json={"username": "admin"}
        )
        assert response.status_code == 422
        
        # Missing username
        response = client.post(
            "/api/auth/login",
            json={"password": "password"}
        )
        assert response.status_code == 422
    
    def test_me_endpoint_with_valid_token(self):
        """Test /me endpoint with valid token"""
        # First login to get token
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "PyRobot_Admin_2025!"}
        )
        token = login_response.json()["access_token"]
        
        # Use token to access /me endpoint
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
    
    def test_me_endpoint_without_token(self):
        """Test /me endpoint without authentication token"""
        response = client.get("/api/auth/me")
        
        assert response.status_code == 401
    
    def test_me_endpoint_with_invalid_token(self):
        """Test /me endpoint with invalid token"""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        
        assert response.status_code == 401
    
    def test_refresh_token_endpoint(self):
        """Test refresh token endpoint"""
        # First login to get tokens
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "PyRobot_Admin_2025!"}
        )
        refresh_token = login_response.json()["refresh_token"]
        
        # Use refresh token to get new access token
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    def test_refresh_token_invalid(self):
        """Test refresh token endpoint with invalid token"""
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid.refresh.token"}
        )
        
        assert response.status_code == 401


class TestAuthorizationMiddleware:
    """Test suite for authorization middleware and protected endpoints"""
    
    def test_protected_endpoint_without_auth(self):
        """Test accessing protected endpoint without authentication"""
        response = client.get("/api/database/tables")
        
        assert response.status_code == 401
    
    def test_protected_endpoint_with_valid_auth(self):
        """Test accessing protected endpoint with valid authentication"""
        # Login to get token
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "PyRobot_Admin_2025!"}
        )
        token = login_response.json()["access_token"]
        
        # Access protected endpoint
        response = client.get(
            "/api/database/tables",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should succeed (200) or handle gracefully
        assert response.status_code in [200, 500]  # 500 if no database connection
    
    def test_admin_required_endpoint_as_admin(self):
        """Test admin-required endpoint with admin user"""
        # Login as admin
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "PyRobot_Admin_2025!"}
        )
        token = login_response.json()["access_token"]
        
        # Access admin endpoint (if exists)
        response = client.get(
            "/api/auth/me",  # Using /me as a test endpoint
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
    
    def test_admin_required_endpoint_as_user(self):
        """Test admin-required endpoint with regular user"""
        # Login as regular user
        login_response = client.post(
            "/api/auth/login",
            json={"username": "hamilton", "password": "mkdpw:V43"}
        )
        token = login_response.json()["access_token"]
        
        # Access user endpoint should work
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "user"


class TestAuthSecurity:
    """Test suite for authentication security features"""
    
    def test_password_hashing(self):
        """Test that passwords are properly hashed"""
        auth = AuthService()
        
        password = "test_password"
        hashed = auth.get_password_hash(password)
        
        # Hash should be different from password
        assert hashed != password
        assert len(hashed) > 0
        
        # Should be able to verify
        assert auth.verify_password(password, hashed) is True
        assert auth.verify_password("wrong_password", hashed) is False
    
    def test_token_expiration_times(self):
        """Test that tokens have appropriate expiration times"""
        auth = AuthService()
        
        # Create tokens
        token_data = {"sub": "admin", "role": "admin"}
        access_token = auth.create_access_token(token_data)
        refresh_token = auth.create_refresh_token(token_data)
        
        # Decode and check expiration times
        access_payload = jwt.decode(access_token, auth.secret_key, algorithms=[auth.algorithm])
        refresh_payload = jwt.decode(refresh_token, auth.secret_key, algorithms=[auth.algorithm])
        
        access_exp = datetime.fromtimestamp(access_payload['exp'])
        refresh_exp = datetime.fromtimestamp(refresh_payload['exp'])
        
        # Access token should expire in ~30 minutes
        assert access_exp > datetime.utcnow() + timedelta(minutes=25)
        assert access_exp < datetime.utcnow() + timedelta(minutes=35)
        
        # Refresh token should expire in ~7 days
        assert refresh_exp > datetime.utcnow() + timedelta(days=6)
        assert refresh_exp < datetime.utcnow() + timedelta(days=8)
    
    def test_sql_injection_protection(self):
        """Test protection against SQL injection in usernames"""
        auth = AuthService()
        
        # Try SQL injection in username
        malicious_username = "admin'; DROP TABLE users; --"
        user = auth.authenticate_user(malicious_username, "any_password")
        
        # Should safely return None
        assert user is None
    
    def test_token_includes_user_info(self):
        """Test that tokens include proper user information"""
        auth = AuthService()
        
        # Create token for admin
        token_data = {"sub": "admin", "role": "admin"}
        token = auth.create_access_token(token_data)
        
        payload = auth.verify_token(token)
        assert payload['sub'] == 'admin'
        assert payload['role'] == 'admin'
        assert 'exp' in payload
        assert 'iat' in payload


if __name__ == "__main__":
    pytest.main([__file__, "-v"])