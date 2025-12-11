"""
Winding Diagnostics Utility

Provides tools to trace and diagnose winding value issues through the processing pipeline.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from ..utils.winding_router import route_by_winding, route_by_winding_str

logger = logging.getLogger(__name__)


class WindingDiagnostics:
    """Diagnostic tools for tracing winding values through processing"""
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize diagnostics with optional storage directory.
        
        Args:
            storage_dir: Path to PDF storage directory (defaults to config)
        """
        if storage_dir:
            self.storage_root = Path(storage_dir)
        else:
            from ..core.config import settings
            self.storage_root = Path(settings.storage_dir)
        
        self.original_dir = self.storage_root / "original"
        self.processed_dir = self.storage_root / "processed"
    
    def trace_winding_flow(
        self,
        input_winding: Any,
        config_dict: Dict[str, Any],
        is_reseller: bool = False
    ) -> Dict[str, Any]:
        """
        Trace how a winding value flows through the processing pipeline.
        
        Args:
            input_winding: The winding value from input JSON
            config_dict: The full configuration dictionary
            is_reseller: Whether this is a reseller order
            
        Returns:
            Dictionary with diagnostic information
        """
        diagnostics = {
            "input": {
                "winding": input_winding,
                "winding_type": type(input_winding).__name__,
                "width": config_dict.get("Width") or config_dict.get("width"),
                "height": config_dict.get("Height") or config_dict.get("height"),
            },
            "processing": {},
            "output": {},
            "errors": []
        }
        
        # Step 1: Parse winding value
        try:
            if input_winding is None:
                diagnostics["processing"]["parsed_winding"] = None
                diagnostics["processing"]["rotation_angle"] = None
                diagnostics["processing"]["needs_rotation"] = False
            else:
                # Try to get rotation angle
                try:
                    rotation = route_by_winding_str(input_winding)
                    diagnostics["processing"]["parsed_winding"] = input_winding
                    diagnostics["processing"]["rotation_angle"] = rotation
                    diagnostics["processing"]["needs_rotation"] = rotation != 0
                    diagnostics["processing"]["should_swap_dimensions"] = rotation in (90, 270)
                except ValueError as e:
                    diagnostics["errors"].append(f"Invalid winding value: {e}")
                    diagnostics["processing"]["parsed_winding"] = input_winding
                    diagnostics["processing"]["rotation_angle"] = None
        except Exception as e:
            diagnostics["errors"].append(f"Error parsing winding: {e}")
        
        # Step 2: Reseller normalization
        if is_reseller:
            diagnostics["output"]["normalized_winding"] = 2
            diagnostics["output"]["winding_changed"] = (
                diagnostics["processing"].get("parsed_winding") != 2
            )
        else:
            diagnostics["output"]["normalized_winding"] = diagnostics["processing"].get("parsed_winding")
            diagnostics["output"]["winding_changed"] = False
        
        # Step 3: Dimension analysis
        input_width = diagnostics["input"]["width"]
        input_height = diagnostics["input"]["height"]
        
        if input_width and input_height:
            diagnostics["dimensions"] = {
                "input": {"width": input_width, "height": input_height},
                "after_rotation": {
                    "width": input_width,
                    "height": input_height
                },
                "note": "Dimensions are NOT swapped in this module - swapping happens downstream"
            }
            
            rotation = diagnostics["processing"].get("rotation_angle")
            if rotation in (90, 270):
                diagnostics["dimensions"]["expected_downstream_swap"] = True
                diagnostics["dimensions"]["expected_final"] = {
                    "width": input_height,
                    "height": input_width
                }
            else:
                diagnostics["dimensions"]["expected_downstream_swap"] = False
                diagnostics["dimensions"]["expected_final"] = {
                    "width": input_width,
                    "height": input_height
                }
        
        return diagnostics
    
    def find_order_files(self, order_reference: str) -> Dict[str, Any]:
        """
        Find all files associated with an order reference.
        
        Args:
            order_reference: Order reference (e.g., "6001949316-2")
            
        Returns:
            Dictionary with file paths and metadata
        """
        results = {
            "order_reference": order_reference,
            "original_files": [],
            "processed_files": [],
            "json_files": [],
            "found": False
        }
        
        # Search original directory
        if self.original_dir.exists():
            for file_path in self.original_dir.glob(f"*{order_reference}*"):
                if file_path.is_file():
                    results["original_files"].append({
                        "path": str(file_path),
                        "name": file_path.name,
                        "size": file_path.stat().st_size,
                        "modified": file_path.stat().st_mtime
                    })
                    results["found"] = True
        
        # Search processed directory
        if self.processed_dir.exists():
            for file_path in self.processed_dir.glob(f"*{order_reference}*"):
                if file_path.is_file():
                    results["processed_files"].append({
                        "path": str(file_path),
                        "name": file_path.name,
                        "size": file_path.stat().st_size,
                        "modified": file_path.stat().st_mtime
                    })
                    results["found"] = True
        
        # Look for JSON files (might be in same directories or elsewhere)
        for directory in [self.original_dir, self.processed_dir, self.storage_root]:
            if directory.exists():
                for file_path in directory.glob(f"*{order_reference}*.json"):
                    if file_path.is_file():
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                json_data = json.load(f)
                            results["json_files"].append({
                                "path": str(file_path),
                                "name": file_path.name,
                                "data": json_data,
                                "winding": json_data.get("Winding") or json_data.get("winding"),
                                "width": json_data.get("Width") or json_data.get("width"),
                                "height": json_data.get("Height") or json_data.get("height"),
                            })
                        except Exception as e:
                            results["json_files"].append({
                                "path": str(file_path),
                                "name": file_path.name,
                                "error": str(e)
                            })
        
        return results
    
    def analyze_order(self, order_reference: str) -> Dict[str, Any]:
        """
        Comprehensive analysis of an order's winding processing.
        
        Args:
            order_reference: Order reference to analyze
            
        Returns:
            Complete diagnostic report
        """
        report = {
            "order_reference": order_reference,
            "files": self.find_order_files(order_reference),
            "analysis": {}
        }
        
        # Analyze JSON files found
        json_files = report["files"]["json_files"]
        if json_files:
            for json_file in json_files:
                if "data" in json_file:
                    config_dict = json_file["data"]
                    input_winding = json_file.get("winding")
                    
                    # Detect if reseller (has Winding key)
                    is_reseller = "Winding" in config_dict or "winding" in config_dict
                    
                    # Trace winding flow
                    diagnostics = self.trace_winding_flow(
                        input_winding,
                        config_dict,
                        is_reseller
                    )
                    
                    report["analysis"][json_file["name"]] = diagnostics
        
        return report

