"""
Experiment Discovery Service

Discovers and manages available Hamilton .med experiment files.
Provides explicit method import and database catalogue access.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from backend.services.scheduling.sqlite_database import get_sqlite_scheduling_database


logger = logging.getLogger(__name__)


class ExperimentDiscoveryService:
    """Service for discovering and managing available Hamilton experiments"""
    
    # Known experiment categories based on naming patterns
    EXPERIMENT_CATEGORIES = {
        "Champions": "Championship Experiments",
        "EvoYeast": "Evolution Yeast Studies",
        "Test": "Test Protocols",
        "Calibration": "System Calibration",
        "Maintenance": "Maintenance Procedures",
        "Custom": "Custom User Protocols"
    }
    
    def __init__(self):
        """Initialize the experiment discovery service"""
        self.db = get_sqlite_scheduling_database()
        
    @staticmethod
    def _method_key(path: str) -> str:
        return os.path.normcase(str(Path(path).resolve())).casefold()

    def preview_methods(self, folder_path: str, relative_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Read host metadata only. Never change the catalogue."""
        folder = Path(folder_path.strip().strip('"')).expanduser()
        if not folder.is_absolute():
            raise ValueError("Enter an absolute folder path on the RobotControl computer.")
        try:
            folder = folder.resolve(strict=True)
            if not folder.is_dir():
                raise ValueError("The selected path is not a folder.")
        except OSError as exc:
            raise ValueError(f"Cannot access the selected folder: {exc}") from exc
        if relative_paths is not None and not relative_paths:
            raise ValueError("Select at least one method to import.")
        if relative_paths is None:
            relative_paths = []
            def scan_error(error):
                raise ValueError(f"Cannot scan the selected folder: {error}")
            for directory, subdirs, names in os.walk(folder, followlinks=False, onerror=scan_error):
                # Do not traverse links/junctions into another tree or a cycle.
                subdirs[:] = [name for name in subdirs if not Path(directory, name).is_symlink()
                              and not Path(directory, name).is_junction()]
                relative_paths.extend(str(Path(directory, name).relative_to(folder))
                                      for name in names if Path(name).suffix.lower() == ".med")
        existing = set()
        existing_rows = {}
        for stored in self.db.get_experiment_methods(valid_only=False):
            try:
                if Path(stored["file_path"]).is_absolute():
                    existing.add(self._method_key(stored["file_path"]))
                    existing_rows.setdefault(self._method_key(stored['file_path']), []).append(stored)
            except (OSError, ValueError):
                # Leave older unverified catalogue entries unchanged; they must not break preview.
                logger.warning("Ignoring an unresolvable catalogue path during import preview")
        methods, seen = [], set()
        for relative in sorted(relative_paths, key=str.casefold):
            row = {"name": Path(relative).stem, "relative_path": relative, "path": None,
                   "size": None, "last_modified": None, "action": "invalid", "reason": None}
            try:
                candidate = Path(relative)
                if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
                    raise ValueError("Use a relative method path inside the selected folder.")
                if candidate.suffix.lower() != ".med":
                    raise ValueError("Select a .med method file.")
                path = (folder / candidate).resolve(strict=True)
                if not path.is_relative_to(folder):
                    raise ValueError("Method resolves outside the selected folder.")
                if path.suffix.lower() != ".med" or not path.is_file():
                    raise ValueError("Select a .med method file.")
                stat = path.stat()
                key = self._method_key(str(path))
                if key in seen:
                    raise ValueError("This method is already included in the selection.")
                seen.add(key)
                matches = existing_rows.get(key, [])
                matches = [item for item in matches if not item.get('archived')] or matches
                if len(matches) > 1:
                    raise ValueError('Multiple catalogue entries resolve to this method; archive duplicate entries in the library first.')
                row.update(name=path.stem, path=str(path), size=stat.st_size,
                           last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                           action="update" if key in existing else "new", archived=bool(matches and matches[0].get('archived')))
            except (OSError, ValueError) as exc:
                row["reason"] = str(exc)
            methods.append(row)
        return {"folder": str(folder), "total_found": len(methods), "methods": methods}

    def import_methods_from_folder(self, folder_path: str, imported_by: str = "system",
                                   relative_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Revalidate selected host paths immediately before writing catalogue metadata."""
        preview = self.preview_methods(folder_path, relative_paths)
        valid = [row for row in preview["methods"] if row["action"] != "invalid"]
        metadata = [{"name": row["name"], "path": row["path"], "file_size": row["size"],
                     "last_modified": row["last_modified"], "category": self._determine_category(row["name"]),
                     "source_folder": preview["folder"], "description": f"Imported from {preview['folder']}",
                     "metadata": {"relative_path": row["relative_path"], "import_timestamp": datetime.now().isoformat()}}
                    for row in valid]
        outcomes = {self._method_key(row["path"]): row
                    for row in self.db.import_experiment_methods(metadata, imported_by)} if metadata else {}
        for row in preview["methods"]:
            outcome = outcomes.get(self._method_key(row["path"])) if row["action"] != "invalid" else None
            row["status"] = outcome["status"] if outcome else "failed"
            row["reason"] = outcome["reason"] if outcome else row["reason"] or "Method was not imported."
        result = self.import_summary(preview["methods"])
        result.update(folder=preview["folder"], imported_by=imported_by, imported_at=datetime.now().isoformat())
        return result

    @staticmethod
    def import_summary(methods: List[Dict[str, Any]]) -> Dict[str, Any]:
        failed = sum(row["status"] == "failed" for row in methods)
        return {"success": bool(methods) and failed == 0, "total_found": len(methods),
                "new_methods": sum(row["status"] == "added" for row in methods),
                "updated_methods": sum(row["status"] == "updated" for row in methods),
                "failed_methods": failed, "methods": methods,
                "errors": [f"{row.get('relative_path') or row.get('path')}: {row['reason']}"
                           for row in methods if row["status"] == "failed"]}

    def get_available_experiments(self) -> List[Dict[str, Any]]:
        """Read available methods from the catalogue."""
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
