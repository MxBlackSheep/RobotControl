"""
PyRobot Simplified Authentication Service

Clean and simple JWT-based authentication service.
Consolidates functionality from web_app/core/auth.py into a simplified interface.
"""

import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from passlib.context import CryptContext
from dataclasses import dataclass
import os
import sys
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import configuration from project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)

# Authentication Configuration
SECRET_KEY = "PyRobot_JWT_Secret_Key_2025_Hamilton_VENUS"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 240  # 4 hours for scientific workflows
REFRESH_TOKEN_EXPIRE_HOURS = 168  # 7 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass
class User:
    """Simple user model"""
    user_id: str
    username: str
    role: str  # "admin" or "user"
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary for JWT payload"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create user from dictionary (JWT payload)"""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            role=data["role"],
            is_active=data.get("is_active", True)
        )


class AuthService:
    """
    Simplified authentication service that consolidates all authentication operations.
    
    Provides:
    - User authentication with JWT tokens
    - Simple admin/user role system
    - Token validation and refresh
    - Clean API for authentication operations
    """
    
    def __init__(self):
        """Initialize the authentication service"""
        # Simple in-memory user store (in production, this could be database-backed)
        self.users_db = {
            "admin": {
                "user_id": "admin_001",
                "username": "admin",
                "role": "admin",
                "password_hash": pwd_context.hash("PyRobot_Admin_2025!"),
                "is_active": True
            },
            "hamilton": {
                "user_id": "hamilton_001", 
                "username": "hamilton",
                "role": "admin",
                "password_hash": pwd_context.hash("mkdpw:V43"),  # Use existing database password
                "is_active": True
            },
            "user": {
                "user_id": "user_001",
                "username": "user",
                "role": "user",
                "password_hash": pwd_context.hash("PyRobot_User_2025!"),
                "is_active": True
            }
        }
        logger.info("AuthService initialized with simplified user management")
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its hash"""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password
        
        Args:
            username: Username to authenticate
            password: Plain text password
            
        Returns:
            User object if authentication successful, None otherwise
        """
        try:
            user_data = self.users_db.get(username)
            if not user_data:
                logger.warning(f"Authentication failed: User '{username}' not found")
                return None
            
            if not self.verify_password(password, user_data["password_hash"]):
                logger.warning(f"Authentication failed: Invalid password for user '{username}'")
                return None
            
            if not user_data["is_active"]:
                logger.warning(f"Authentication failed: User '{username}' is inactive")
                return None
            
            logger.info(f"User '{username}' authenticated successfully with role '{user_data['role']}'")
            return User(
                user_id=user_data["user_id"],
                username=user_data["username"],
                role=user_data["role"],
                is_active=user_data["is_active"]
            )
        except Exception as e:
            logger.error(f"Authentication error for user '{username}': {e}")
            return None
    
    def create_access_token(self, user: User, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create JWT access token
        
        Args:
            user: User object
            expires_delta: Optional custom expiration time
            
        Returns:
            JWT access token string
        """
        try:
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            
            to_encode = user.to_dict().copy()
            to_encode.update({
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "access"
            })
            
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            logger.info(f"Access token created for user '{user.username}' (expires: {expire})")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error creating access token for user '{user.username}': {e}")
            raise
    
    def create_refresh_token(self, user: User) -> str:
        """
        Create JWT refresh token
        
        Args:
            user: User object
            
        Returns:
            JWT refresh token string
        """
        try:
            expire = datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
            
            to_encode = {
                "user_id": user.user_id,
                "username": user.username,
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "refresh"
            }
            
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            logger.info(f"Refresh token created for user '{user.username}' (expires: {expire})")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Error creating refresh token for user '{user.username}': {e}")
            raise
    
    def verify_token(self, token: str) -> Optional[User]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            User object if token is valid, None otherwise
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check token type
            if payload.get("type") != "access":
                logger.warning("Invalid token type")
                return None
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
                logger.warning("Token has expired")
                return None
            
            # Create user from payload
            user = User.from_dict(payload)
            
            # Verify user still exists and is active
            user_data = self.users_db.get(user.username)
            if not user_data or not user_data["is_active"]:
                logger.warning(f"User '{user.username}' no longer active")
                return None
            
            return user
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Create new access token from refresh token
        
        Args:
            refresh_token: JWT refresh token string
            
        Returns:
            New access token string if refresh successful, None otherwise
        """
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # Check token type
            if payload.get("type") != "refresh":
                logger.warning("Invalid refresh token type")
                return None
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
                logger.warning("Refresh token has expired")
                return None
            
            # Get user info
            username = payload.get("username")
            user_data = self.users_db.get(username)
            if not user_data or not user_data["is_active"]:
                logger.warning(f"User '{username}' no longer active")
                return None
            
            # Create new user object and access token
            user = User(
                user_id=user_data["user_id"],
                username=user_data["username"],
                role=user_data["role"],
                is_active=user_data["is_active"]
            )
            
            new_access_token = self.create_access_token(user)
            logger.info(f"Access token refreshed for user '{username}'")
            return new_access_token
            
        except jwt.ExpiredSignatureError:
            logger.warning("Refresh token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid refresh token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None
    
    def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Complete login process with token generation
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Dictionary with tokens and user info if successful, None otherwise
        """
        # Authenticate user
        user = self.authenticate_user(username, password)
        if not user:
            return None
        
        # Create tokens
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
            "user": user.to_dict()
        }
    
    def get_user_list(self) -> List[Dict[str, Any]]:
        """
        Get list of all users (admin only function)
        
        Returns:
            List of user information dictionaries
        """
        return [
            {
                "user_id": user_data["user_id"],
                "username": user_data["username"],
                "role": user_data["role"],
                "is_active": user_data["is_active"]
            }
            for user_data in self.users_db.values()
        ]
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by user ID
        
        Args:
            user_id: User ID to lookup
            
        Returns:
            User object if found, None otherwise
        """
        for user_data in self.users_db.values():
            if user_data["user_id"] == user_id:
                return User(
                    user_id=user_data["user_id"],
                    username=user_data["username"],
                    role=user_data["role"],
                    is_active=user_data["is_active"]
                )
        return None
    
    def is_admin(self, user: User) -> bool:
        """
        Check if user has admin role
        
        Args:
            user: User object
            
        Returns:
            True if user is admin, False otherwise
        """
        return user.role == "admin"
    
    def get_auth_stats(self) -> Dict[str, Any]:
        """
        Get authentication service statistics
        
        Returns:
            Dictionary with authentication statistics
        """
        return {
            "total_users": len(self.users_db),
            "active_users": sum(1 for user in self.users_db.values() if user["is_active"]),
            "admin_users": sum(1 for user in self.users_db.values() if user["role"] == "admin"),
            "user_list": [user["username"] for user in self.users_db.values() if user["is_active"]]
        }
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all users with detailed information (admin only)
        
        Returns:
            List of user dictionaries with full details
        """
        return [
            {
                "username": user_data["username"],
                "role": user_data["role"],
                "is_active": user_data["is_active"],
                "last_login": None,  # Could be implemented with login tracking
                "created_at": None   # Could be implemented with user creation tracking
            }
            for user_data in self.users_db.values()
        ]
    
    def toggle_user_active(self, username: str) -> bool:
        """
        Toggle user active status (admin only)
        
        Args:
            username: Username to toggle
            
        Returns:
            True if user was found and toggled, False otherwise
        """
        if username in self.users_db:
            self.users_db[username]["is_active"] = not self.users_db[username]["is_active"]
            new_status = "activated" if self.users_db[username]["is_active"] else "deactivated"
            logger.info(f"User '{username}' {new_status}")
            return True
        return False


# Global service instance
_auth_service = None


def get_auth_service() -> AuthService:
    """Get singleton authentication service instance"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
        logger.info("AuthService singleton instance created")
    return _auth_service


# Create security scheme
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI dependency to get current authenticated user from JWT token
    
    Args:
        credentials: JWT token from Authorization header
        
    Returns:
        User dictionary
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    service = get_auth_service()
    user = service.verify_token(credentials.credentials)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user.to_dict()

def get_current_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency to get current authenticated admin user
    
    Args:
        current_user: Current user from get_current_user dependency
        
    Returns:
        Admin user dictionary
        
    Raises:
        HTTPException: If user is not an admin
    """
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user

# Convenience functions for backward compatibility
def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user (backward compatibility)"""
    service = get_auth_service()
    return service.authenticate_user(username, password)


def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """Create access token (backward compatibility)"""
    service = get_auth_service()
    return service.create_access_token(user, expires_delta)


def verify_token(token: str) -> Optional[User]:
    """Verify token (backward compatibility)"""
    service = get_auth_service()
    return service.verify_token(token)


if __name__ == "__main__":
    # Example usage
    service = get_auth_service()
    
    print("=== PyRobot Simplified Authentication Service ===")
    
    # Test authentication
    result = service.login("admin", "PyRobot_Admin_2025!")
    if result:
        print(f"Login successful for user: {result['user']['username']}")
        print(f"Token type: {result['token_type']}")
        print(f"Expires in: {result['expires_in']} seconds")
        
        # Test token verification
        user = service.verify_token(result["access_token"])
        if user:
            print(f"Token verified for user: {user.username} (role: {user.role})")
    
    # Get stats
    stats = service.get_auth_stats()
    print(f"Auth Stats: {stats['total_users']} users, {stats['admin_users']} admins")
    
    print("=== Authentication Service Example Complete ===")