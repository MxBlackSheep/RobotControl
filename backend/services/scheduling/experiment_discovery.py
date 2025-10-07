"""
Experiment Discovery Service

Discovers and manages available Hamilton .med experiment files.
Provides both local file system scanning and database tracking for remote access.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from backend.services.scheduling.sqlite_database import get_sqlite_scheduling_database

logger = logging.getLogger(__name__)


class ExperimentFile:
    """Represents a discovered experiment file"""
    
    def __init__(self, name: str, path: str, category: str = "general", 
                 description: str = "", last_modified: Optional[datetime] = None):
        self.name = name
        self.path = path
        self.category = category
        self.description = description
        self.last_modified = last_modified or datetime.now()
        self.file_size = 0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "category": self.category,
            "description": self.description,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "file_size": self.file_size
        }


class ExperimentDiscoveryService:
    """Service for discovering and managing available Hamilton experiments"""
    
    # Common Hamilton experiment paths
    DEFAULT_SEARCH_PATHS = [
        r"C:\Program Files (x86)\HAMILTON\Methods",
        r"C:\Program Files\HAMILTON\Methods",
        r"C:\Hamilton\Methods",
        r"D:\Hamilton\Methods",
        r".\methods",  # Local methods folder
        r".\experiments"  # Alternative local folder
    ]
    
    # Known experiment categories based on naming patterns
    EXPERIMENT_CATEGORIES = {
        "Champions": "Championship Experiments",
        "EvoYeast": "Evolution Yeast Studies",
        "Test": "Test Protocols",
        "Calibration": "System Calibration",
        "Maintenance": "Maintenance Procedures",
        "Custom": "Custom User Protocols"
    }
    
    # Common database flags used as prerequisites
    AVAILABLE_PREREQUISITES = [
        {
            "flag": "ScheduledToRun",
            "description": "Reset ScheduledToRun flags and mark this experiment prior to execution",
            "table": "Experiments"
        },
        {
            "flag": "ResetHamiltonTables",
            "description": "Reset Hamilton SQL Server tables for the selected experiment before running",
            "table": "HamiltonProcedures"
        }
    ]
    
    def __init__(self):
        """Initialize the experiment discovery service"""
        self.discovered_experiments: List[ExperimentFile] = []
        self._cache_file = "data/experiment_cache.json"
        self._last_scan = None
        self.db = get_sqlite_scheduling_database()
        
    def scan_for_experiments(self, custom_paths: Optional[List[str]] = None) -> List[ExperimentFile]:
        """
        Scan file system for .med experiment files
        
        Args:
            custom_paths: Optional list of additional paths to search
            
        Returns:
            List of discovered ExperimentFile objects
        """
        search_paths = self.DEFAULT_SEARCH_PATHS.copy()
        if custom_paths:
            search_paths.extend(custom_paths)
            
        discovered = []
        
        for search_path in search_paths:
            try:
                path = Path(search_path)
                if not path.exists():
                    continue
                    
                # Search for .med files
                for med_file in path.rglob("*.med"):
                    try:
                        # Extract experiment info
                        experiment_name = med_file.stem
                        full_path = str(med_file.absolute())
                        
                        # Determine category based on name
                        category = self._determine_category(experiment_name)
                        
                        # Get file metadata
                        stat = med_file.stat()
                        
                        experiment = ExperimentFile(
                            name=experiment_name,
                            path=full_path,
                            category=category,
                            description=f"Hamilton method file from {search_path}",
                            last_modified=datetime.fromtimestamp(stat.st_mtime)
                        )
                        experiment.file_size = stat.st_size
                        
                        discovered.append(experiment)
                        logger.debug(f"Discovered experiment: {experiment_name} at {full_path}")
                        
                    except Exception as e:
                        logger.warning(f"Error processing {med_file}: {e}")
                        
            except Exception as e:
                logger.warning(f"Error scanning path {search_path}: {e}")
                
        self.discovered_experiments = discovered
        self._last_scan = datetime.now()
        
        # Cache the results for remote access
        self._save_cache()
        
        logger.info(f"Discovered {len(discovered)} experiment files")
        return discovered
        
    def import_methods_from_folder(self, folder_path: str, imported_by: str = "system") -> Dict[str, Any]:
        """
        Import all .med files from a specified folder into the database
        
        Args:
            folder_path: Path to folder containing .med files
            imported_by: Username of who is importing the methods
            
        Returns:
            Dictionary with import results and statistics
        """
        results = {
            "success": False,
            "folder": folder_path,
            "imported_by": imported_by,
            "imported_at": datetime.now().isoformat(),
            "new_methods": 0,
            "updated_methods": 0,
            "failed_methods": 0,
            "total_found": 0,
            "methods": [],
            "errors": []
        }
        
        try:
            folder = Path(folder_path)
            if not folder.exists():
                results["errors"].append(f"Folder does not exist: {folder_path}")
                return results
                
            if not folder.is_dir():
                results["errors"].append(f"Path is not a folder: {folder_path}")
                return results
            
            # Find all .med files in the folder (including subdirectories)
            med_files = list(folder.rglob("*.med"))
            results["total_found"] = len(med_files)
            
            if len(med_files) == 0:
                results["errors"].append(f"No .med files found in {folder_path}")
                return results
            
            logger.info(f"Found {len(med_files)} .med files in {folder_path}")
            
            # Process each file
            methods_to_import = []
            for med_file in med_files:
                try:
                    stat = med_file.stat()
                    experiment_name = med_file.stem
                    
                    method_data = {
                        "name": experiment_name,
                        "path": str(med_file.absolute()),
                        "category": self._determine_category(experiment_name),
                        "description": f"Imported from {folder_path}",
                        "file_size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "source_folder": str(folder.absolute()),
                        "metadata": {
                            "relative_path": str(med_file.relative_to(folder)),
                            "import_timestamp": datetime.now().isoformat()
                        }
                    }
                    
                    methods_to_import.append(method_data)
                    results["methods"].append({
                        "name": experiment_name,
                        "path": str(med_file.absolute()),
                        "size": stat.st_size
                    })
                    
                except Exception as e:
                    results["failed_methods"] += 1
                    results["errors"].append(f"Failed to process {med_file}: {str(e)}")
                    logger.warning(f"Failed to process {med_file}: {e}")
            
            # Import to database
            if methods_to_import:
                new_count, updated_count = self.db.import_experiment_methods(
                    methods_to_import, 
                    imported_by
                )
                results["new_methods"] = new_count
                results["updated_methods"] = updated_count
                results["success"] = True
                
                # Clear cache to force refresh
                self.discovered_experiments = []
                self._last_scan = None
                
                logger.info(f"Imported {new_count} new and {updated_count} updated methods from {folder_path}")
            
        except Exception as e:
            results["errors"].append(f"Import failed: {str(e)}")
            logger.error(f"Failed to import methods from {folder_path}: {e}")
            
        return results
    
    def get_available_experiments(self, use_cache: bool = True, use_database: bool = True) -> List[Dict[str, Any]]:
        """
        Get list of available experiments
        
        Args:
            use_cache: If True, use cached results if available
            use_database: If True, load from database instead of file scan
            
        Returns:
            List of experiment dictionaries
        """
        if use_database:
            # Get experiments from database (preferred method)
            db_experiments = self.db.get_experiment_methods()
            
            # Convert database format to expected format
            experiments = []
            for exp in db_experiments:
                experiments.append({
                    "name": exp.get("method_name", ""),
                    "path": exp.get("file_path", ""),
                    "category": exp.get("category", "Custom"),
                    "description": exp.get("description", ""),
                    "last_modified": exp.get("file_modified"),
                    "file_size": exp.get("file_size", 0),
                    "imported_at": exp.get("imported_at"),
                    "imported_by": exp.get("imported_by"),
                    "use_count": exp.get("use_count", 0),
                    "last_used": exp.get("last_used")
                })
            
            return experiments
            
        # Fall back to file system scan
        if use_cache and self._load_cache():
            return [exp.to_dict() for exp in self.discovered_experiments]
            
        # Perform fresh scan
        self.scan_for_experiments()
        return [exp.to_dict() for exp in self.discovered_experiments]
        
    def get_experiment_by_name(self, name: str) -> Optional[ExperimentFile]:
        """
        Get experiment by name
        
        Args:
            name: Experiment name (without .med extension)
            
        Returns:
            ExperimentFile object or None if not found
        """
        for experiment in self.discovered_experiments:
            if experiment.name.lower() == name.lower():
                return experiment
        return None
        
    def get_experiments_by_category(self, category: str) -> List[ExperimentFile]:
        """
        Get all experiments in a specific category
        
        Args:
            category: Category name
            
        Returns:
            List of ExperimentFile objects in that category
        """
        return [exp for exp in self.discovered_experiments 
                if exp.category.lower() == category.lower()]
        
    def get_available_prerequisites(self) -> List[Dict[str, Any]]:
        """
        Get list of available prerequisite flags
        
        Returns:
            List of prerequisite flag definitions
        """
        return self.AVAILABLE_PREREQUISITES.copy()
        
    def validate_experiment_path(self, path: str) -> bool:
        """
        Validate that an experiment path exists and is accessible
        
        Args:
            path: Path to experiment .med file
            
        Returns:
            True if path is valid and accessible
        """
        try:
            path_obj = Path(path)
            return path_obj.exists() and path_obj.suffix.lower() == '.med'
        except Exception:
            return False
            
    def _determine_category(self, experiment_name: str) -> str:
        """
        Determine experiment category based on name patterns
        
        Args:
            experiment_name: Name of the experiment
            
        Returns:
            Category string
        """
        name_upper = experiment_name.upper()
        
        for pattern, category in self.EXPERIMENT_CATEGORIES.items():
            if pattern.upper() in name_upper:
                return category
                
        return "Custom User Protocols"
        
    def _save_cache(self):
        """Save discovered experiments to cache file"""
        try:
            cache_data = {
                "last_scan": self._last_scan.isoformat() if self._last_scan else None,
                "experiments": [exp.to_dict() for exp in self.discovered_experiments]
            }
            
            # Ensure data directory exists
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            
            with open(self._cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
            logger.debug(f"Saved {len(self.discovered_experiments)} experiments to cache")
            
        except Exception as e:
            logger.warning(f"Failed to save experiment cache: {e}")
            
    def _load_cache(self) -> bool:
        """
        Load experiments from cache file
        
        Returns:
            True if cache loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(self._cache_file):
                return False
                
            with open(self._cache_file, 'r') as f:
                cache_data = json.load(f)
                
            # Check cache age (refresh if older than 1 hour)
            if cache_data.get("last_scan"):
                last_scan = datetime.fromisoformat(cache_data["last_scan"])
                if (datetime.now() - last_scan).total_seconds() > 3600:
                    logger.debug("Cache is older than 1 hour, refreshing")
                    return False
                    
            # Load experiments from cache
            self.discovered_experiments = []
            for exp_data in cache_data.get("experiments", []):
                experiment = ExperimentFile(
                    name=exp_data["name"],
                    path=exp_data["path"],
                    category=exp_data.get("category", "Custom"),
                    description=exp_data.get("description", ""),
                    last_modified=datetime.fromisoformat(exp_data["last_modified"]) 
                                 if exp_data.get("last_modified") else None
                )
                experiment.file_size = exp_data.get("file_size", 0)
                self.discovered_experiments.append(experiment)
                
            self._last_scan = last_scan
            logger.debug(f"Loaded {len(self.discovered_experiments)} experiments from cache")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load experiment cache: {e}")
            return False
            

# Singleton instance
_discovery_service = None

def get_experiment_discovery_service() -> ExperimentDiscoveryService:
    """Get singleton instance of experiment discovery service"""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = ExperimentDiscoveryService()
        # No automatic scanning - users should manually import experiments
        # This prevents duplicate imports and gives users control
        logger.info("Experiment discovery service initialized (manual import mode)")
    return _discovery_service