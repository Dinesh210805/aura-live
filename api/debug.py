"""
Debug API Endpoints - Live inspection for debugging.

Provides real-time access to system state, perception data,
and execution metrics without diving into logs.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response

from utils.logger import get_logger
from utils.unified_logger import get_unified_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/state")
async def get_debug_state() -> Dict[str, Any]:
    """
    Get comprehensive system state for debugging.
    
    Returns current state of device, models, and services.
    """
    state = {
        "timestamp": datetime.now().isoformat(),
        "device": await _get_device_state(),
        "models": _get_model_health(),
        "perception": _get_perception_state(),
        "services": _get_service_status(),
    }
    
    return state


@router.get("/device")
async def get_device_debug() -> Dict[str, Any]:
    """Get detailed device debug information."""
    return await _get_device_state()


@router.get("/ui-tree")
async def get_last_ui_tree() -> Dict[str, Any]:
    """
    Get last captured UI tree for inspection.
    
    Useful for debugging element finding issues.
    """
    try:
        from services.real_accessibility import real_accessibility_service
        
        ui_tree = real_accessibility_service.last_ui_analysis
        
        if not ui_tree:
            return {
                "available": False,
                "message": "No UI tree captured yet",
            }
        
        # Extract useful stats
        nodes = ui_tree.get("nodes", [])
        clickable = [n for n in nodes if n.get("clickable")]
        with_text = [n for n in nodes if n.get("text") or n.get("contentDescription")]
        
        return {
            "available": True,
            "captured_at": ui_tree.get("timestamp", "unknown"),
            "package": ui_tree.get("packageName") or ui_tree.get("package"),
            "activity": ui_tree.get("activityName") or ui_tree.get("activity"),
            "stats": {
                "total_nodes": len(nodes),
                "clickable_nodes": len(clickable),
                "nodes_with_text": len(with_text),
            },
            "sample_nodes": _sample_nodes(nodes, limit=10),
            "full_tree": ui_tree,
        }
    except Exception as e:
        logger.error(f"Error getting UI tree: {e}")
        return {
            "available": False,
            "error": str(e),
        }


@router.get("/screenshot")
async def get_screenshot_info() -> Dict[str, Any]:
    """
    Get information about last screenshot (not the actual image).
    
    Use /device/screenshot to get the actual image.
    """
    try:
        from services.real_accessibility import real_accessibility_service
        
        screenshot_data = real_accessibility_service.last_screenshot
        
        if not screenshot_data:
            return {
                "available": False,
                "message": "No screenshot captured yet",
            }
        
        screenshot = screenshot_data.screenshot if hasattr(screenshot_data, 'screenshot') else screenshot_data
        
        return {
            "available": True,
            "size_bytes": len(screenshot) if screenshot else 0,
            "size_kb": round(len(screenshot) / 1024, 2) if screenshot else 0,
            "captured_at": getattr(screenshot_data, 'timestamp', 'unknown'),
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }


@router.get("/perception")
async def get_perception_debug() -> Dict[str, Any]:
    """Get perception pipeline debug information."""
    return _get_perception_state()


@router.get("/detections")
async def get_last_detections() -> Dict[str, Any]:
    """
    Get last OmniParser CV detections.
    
    Returns bounding boxes and labels from last detection run.
    """
    try:
        from perception import get_perception_pipeline
        
        _, _, _, create_pipeline = get_perception_pipeline()
        
        # Try to get cached detections
        # This would need to be stored in the pipeline
        return {
            "available": False,
            "message": "Detections only available during active perception. Run a command first.",
            "hint": "Check perception metrics at /debug/perception for historical stats",
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
        }


@router.get("/metrics")
async def get_performance_metrics() -> Dict[str, Any]:
    """Get performance metrics from perception pipeline."""
    try:
        from perception import get_perception_pipeline
        from services.vlm import VLMService
        from config.settings import get_settings
        
        settings = get_settings()
        vlm_service = VLMService(settings)
        
        _, _, _, create_pipeline = get_perception_pipeline()
        pipeline = create_pipeline(vlm_service)
        
        return {
            "perception": pipeline.metrics.to_dict(),
            "message": "Metrics accumulated since server start",
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "Could not retrieve metrics",
        }


@router.get("/errors/recent")
async def get_recent_errors(limit: int = 10) -> Dict[str, Any]:
    """
    Get recent error contexts.
    
    Returns structured error information for debugging.
    """
    # This would need a persistent error store
    # For now, return guidance
    return {
        "message": "Check logs/command_log_*.txt for detailed error contexts",
        "hint": "Error contexts are logged with full state on failures",
        "log_directory": "logs/",
    }


@router.post("/clear-cache")
async def clear_perception_cache() -> Dict[str, str]:
    """Clear perception pipeline caches."""
    try:
        # Clear any cached perception data
        from services.real_accessibility import real_accessibility_service
        
        # Reset screenshot freshness
        if hasattr(real_accessibility_service, '_last_screenshot_time'):
            real_accessibility_service._last_screenshot_time = 0
        
        return {
            "status": "success",
            "message": "Perception caches cleared",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/config")
async def get_debug_config() -> Dict[str, Any]:
    """Get current configuration (redacted)."""
    try:
        from config.settings import get_settings
        
        settings = get_settings()
        
        return {
            "llm_provider": settings.default_llm_provider,
            "vlm_provider": settings.default_vlm_provider,
            "llm_model": settings.default_llm_model,
            "vlm_model": settings.default_vlm_model,
            "perception_modality": settings.default_perception_modality,
            "use_universal_agent": settings.use_universal_agent,
            "parallel_execution": settings.enable_parallel_execution,
            "provider_fallback": settings.enable_provider_fallback,
            "langsmith_enabled": settings.langchain_tracing_v2,
            "langsmith_project": settings.langchain_project,
            "log_level": settings.log_level,
        }
    except Exception as e:
        return {"error": str(e)}


# Helper functions

async def _get_device_state() -> Dict[str, Any]:
    """Get current device state."""
    try:
        from services.real_accessibility import real_accessibility_service
        
        device_info = real_accessibility_service.device_info
        
        if not device_info:
            return {
                "connected": False,
                "message": "No device connected",
            }
        
        # Get screenshot freshness
        screenshot_data = real_accessibility_service.last_screenshot
        screenshot_age = None
        
        if screenshot_data and hasattr(screenshot_data, 'timestamp'):
            try:
                screenshot_age = time.time() - screenshot_data.timestamp
            except Exception:
                pass
        
        return {
            "connected": True,
            "device_id": getattr(device_info, 'deviceId', 'unknown'),
            "model": getattr(device_info, 'model', 'unknown'),
            "manufacturer": getattr(device_info, 'manufacturer', 'unknown'),
            "android_version": getattr(device_info, 'androidVersion', 'unknown'),
            "screen_width": getattr(device_info, 'screenWidth', None),
            "screen_height": getattr(device_info, 'screenHeight', None),
            "screenshot_age_seconds": round(screenshot_age, 1) if screenshot_age else None,
            "ui_tree_available": real_accessibility_service.last_ui_analysis is not None,
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }


def _get_model_health() -> Dict[str, Any]:
    """Check model provider health."""
    health = {}
    
    # Check Groq
    try:
        from config.settings import get_settings
        settings = get_settings()
        
        health["groq"] = {
            "configured": bool(settings.groq_api_key),
            "default_model": settings.default_llm_model,
        }
    except Exception as e:
        health["groq"] = {"error": str(e)}
    
    # Check Gemini  
    try:
        from config.settings import get_settings
        settings = get_settings()
        
        health["gemini"] = {
            "configured": bool(settings.gemini_api_key),
            "default_model": settings.default_vlm_model,
        }
    except Exception as e:
        health["gemini"] = {"error": str(e)}
    
    return health


def _get_perception_state() -> Dict[str, Any]:
    """Get perception pipeline state."""
    try:
        from config.settings import get_settings
        settings = get_settings()
        
        state = {
            "default_modality": settings.default_perception_modality,
            "fast_apps": settings.fast_perception_apps,
        }
        
        # Try to get pipeline metrics
        try:
            from perception import get_perception_pipeline
            from services.vlm import VLMService
            
            vlm_service = VLMService(settings)
            _, _, _, create_pipeline = get_perception_pipeline()
            pipeline = create_pipeline(vlm_service)
            
            state["metrics"] = pipeline.metrics.to_dict()
        except Exception as e:
            state["metrics_error"] = str(e)
        
        return state
    except Exception as e:
        return {"error": str(e)}


def _get_service_status() -> Dict[str, Any]:
    """Get status of various services."""
    services = {}
    
    # Check accessibility service
    try:
        from services.real_accessibility import real_accessibility_service
        services["accessibility"] = {
            "running": True,
            "device_connected": real_accessibility_service.device_info is not None,
        }
    except Exception as e:
        services["accessibility"] = {"error": str(e)}
    
    # Check graph app
    try:
        from main import graph_app
        services["graph"] = {
            "compiled": graph_app is not None,
        }
    except Exception:
        services["graph"] = {"compiled": False}
    
    return services


def _sample_nodes(nodes: List[Dict], limit: int = 10) -> List[Dict[str, Any]]:
    """Sample interesting nodes from UI tree for debugging."""
    # Prioritize clickable nodes with text
    clickable = [n for n in nodes if n.get("clickable") and (n.get("text") or n.get("contentDescription"))]
    
    sampled = []
    for node in clickable[:limit]:
        sampled.append({
            "text": node.get("text") or node.get("contentDescription"),
            "class": node.get("className", "").split(".")[-1],
            "bounds": node.get("bounds"),
            "clickable": node.get("clickable"),
        })
    
    return sampled


# ============================================================================
# UNIFIED LOGGING ENDPOINTS (God-Level Debugging)
# ============================================================================

@router.get("/unified-logs")
async def get_unified_logs(
    query: Optional[str] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get unified logs from all sources (terminal, LangSmith, command logs).
    
    Query params:
        - query: Search in log messages
        - level: Filter by level (INFO, ERROR, WARNING, DEBUG)
        - source: Filter by source (terminal, langsmith, command_log, error, perf)
        - limit: Max entries to return (default 100)
    """
    try:
        unified = get_unified_logger()
        entries = unified.search(query=query, level=level, source=source, limit=limit)
        
        return {
            "total": len(entries),
            "entries": [e.to_dict() for e in entries]
        }
    except Exception as e:
        logger.error(f"Failed to get unified logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve logs")


@router.get("/unified-logs/timeline")
async def get_unified_timeline(since: Optional[float] = None, limit: int = 50) -> Dict[str, Any]:
    """
    Get timeline view of unified logs.
    
    Query params:
        - since: Unix timestamp to filter from (optional)
        - limit: Max entries (default 50)
    """
    try:
        unified = get_unified_logger()
        timeline = unified.get_timeline(since=since, limit=limit)
        
        return {"timeline": timeline}
    except Exception as e:
        logger.error(f"Failed to get timeline: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve timeline")


@router.get("/unified-logs/trace/{trace_id}")
async def get_trace_logs(trace_id: str) -> Dict[str, Any]:
    """
    Get all logs for a specific trace ID.
    
    Shows everything that happened in a single execution,
    cross-referenced across all log sources.
    """
    try:
        unified = get_unified_logger()
        entries = unified.get_by_trace(trace_id)
        
        if not entries:
            raise HTTPException(status_code=404, detail=f"No logs found for trace {trace_id}")
        
        return {
            "trace_id": trace_id,
            "count": len(entries),
            "entries": [e.to_dict() for e in entries]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trace logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trace logs")


@router.get("/unified-logs/export/html")
async def export_logs_html() -> Response:
    """
    Export unified logs as interactive HTML viewer.
    
    Opens a beautiful web page with:
    - Searchable logs
    - Color-coded by level
    - Grouped by trace
    - Links to LangSmith
    """
    try:
        unified = get_unified_logger()
        filepath = unified.export_html()
        
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return Response(content=html_content, media_type="text/html")
    except Exception as e:
        logger.error(f"Failed to export HTML: {e}")
        raise HTTPException(status_code=500, detail="Failed to export logs")


@router.get("/unified-logs/export/json")
async def export_logs_json() -> Dict[str, Any]:
    """Export unified logs as JSON file."""
    try:
        unified = get_unified_logger()
        filepath = unified.export_json()
        
        return {
            "status": "exported",
            "filepath": filepath,
            "entries": len(unified.entries)
        }
    except Exception as e:
        logger.error(f"Failed to export JSON: {e}")
        raise HTTPException(status_code=500, detail="Failed to export logs")
