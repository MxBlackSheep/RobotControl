"""
Service for managing embedded static resources in single-exe mode.
Provides caching and efficient serving of embedded frontend files.
"""

import hashlib
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging

try:
    from backend.embedded_static import get_embedded_file, list_embedded_files, is_embedded_mode
except ImportError:
    # Fallback for when embedded_static doesn't exist yet
    def get_embedded_file(path: str) -> Optional[Dict]:
        return None
    def list_embedded_files() -> list:
        return []
    def is_embedded_mode() -> bool:
        return False

logger = logging.getLogger(__name__)

class EmbeddedResourceManager:
    """Manages embedded static resources with caching and ETags."""
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._etag_cache: Dict[str, str] = {}
        self._is_embedded = is_embedded_mode()
        
        if self._is_embedded:
            logger.info(f"Embedded mode active with {len(list_embedded_files())} files")
        else:
            logger.info("Running in development mode - serving files from disk")
    
    def is_embedded(self) -> bool:
        """Check if running in embedded mode."""
        return self._is_embedded
    
    def get_resource(self, path: str) -> Optional[Tuple[bytes, str, str]]:
        """
        Get an embedded resource by path.
        
        Args:
            path: URL path of the resource
            
        Returns:
            Tuple of (content, mime_type, etag) or None if not found
        """
        # Normalize path
        if not path:
            path = '/'
        if not path.startswith('/'):
            path = '/' + path
            
        # Check cache first
        if path in self._cache:
            cached = self._cache[path]
            return cached['content'], cached['mime_type'], cached['etag']
        
        # Get from embedded files
        file_data = get_embedded_file(path)
        if not file_data:
            # Try without leading slash
            file_data = get_embedded_file(path[1:])
        
        if not file_data:
            # Special handling for root path
            if path == '/' or path == '':
                file_data = get_embedded_file('/index.html')
        
        if not file_data:
            return None
        
        # Generate ETag based on content
        content = file_data['content']
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        etag = self._generate_etag(content)
        mime_type = file_data.get('mime_type', 'application/octet-stream')
        
        # Cache the result
        self._cache[path] = {
            'content': content,
            'mime_type': mime_type,
            'etag': etag,
            'cached_at': datetime.now()
        }
        self._etag_cache[path] = etag
        
        return content, mime_type, etag
    
    def _generate_etag(self, content: bytes) -> str:
        """Generate ETag for content."""
        return f'"{hashlib.md5(content).hexdigest()}"'
    
    def check_etag(self, path: str, client_etag: str) -> bool:
        """
        Check if client's ETag matches current resource.
        
        Args:
            path: Resource path
            client_etag: ETag from client's If-None-Match header
            
        Returns:
            True if ETags match (resource not modified)
        """
        if not client_etag:
            return False
        
        # Get current ETag
        if path in self._etag_cache:
            current_etag = self._etag_cache[path]
        else:
            resource = self.get_resource(path)
            if not resource:
                return False
            _, _, current_etag = resource
        
        return client_etag == current_etag
    
    def list_resources(self) -> list:
        """List all available embedded resources."""
        return list_embedded_files()
    
    def clear_cache(self):
        """Clear the resource cache."""
        self._cache.clear()
        self._etag_cache.clear()
        logger.info("Resource cache cleared")
    
    def get_cache_headers(self, mime_type: str) -> Dict[str, str]:
        """
        Get appropriate cache headers for a MIME type.
        
        Args:
            mime_type: MIME type of the resource
            
        Returns:
            Dictionary of cache headers
        """
        headers = {}
        
        # Aggressive caching for static assets
        if any(mime_type.startswith(t) for t in ['image/', 'font/', 'application/javascript', 'text/css']):
            # Cache for 1 year
            headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif mime_type == 'text/html':
            # Don't cache HTML to ensure updates are seen
            headers['Cache-Control'] = 'no-cache, must-revalidate'
        else:
            # Moderate caching for other resources
            headers['Cache-Control'] = 'public, max-age=3600'
        
        return headers
    
    def get_resource_info(self, path: str) -> Optional[Dict]:
        """
        Get information about a resource without loading its content.
        
        Args:
            path: Resource path
            
        Returns:
            Dictionary with resource metadata or None
        """
        file_data = get_embedded_file(path)
        if not file_data:
            return None
        
        return {
            'path': path,
            'mime_type': file_data.get('mime_type', 'application/octet-stream'),
            'size': file_data.get('size', 0),
            'compressed': file_data.get('compressed', False)
        }

# Global instance
_resource_manager: Optional[EmbeddedResourceManager] = None

def get_resource_manager() -> EmbeddedResourceManager:
    """Get or create the global resource manager instance."""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = EmbeddedResourceManager()
    return _resource_manager