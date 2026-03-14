"""
Workflow Visualization API.

Provides endpoints for visualizing agent workflow execution.
"""

from typing import Dict, List, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import time
import os

from constants import API_PREFIX
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix=f"{API_PREFIX}/workflow", tags=["Workflow"])

# In-memory storage for workflow sessions
# In production, use Redis or a database
workflow_sessions: Dict[str, Dict[str, Any]] = {}


def store_workflow_state(session_id: str, state: Dict[str, Any]):
    """Store workflow state for visualization."""
    workflow_sessions[session_id] = {
        "session_id": session_id,
        "timestamp": state.get("start_time", time.time()),
        "transcript": state.get("transcript", ""),
        "status": state.get("status", "running"),
        "workflow_steps": state.get("workflow_steps", []),
        "used_agents": state.get("used_agents", []),
        "start_time": state.get("start_time"),
        "end_time": state.get("end_time"),
        "intent": state.get("intent"),
        "plan": state.get("plan"),
        "error_message": state.get("error_message"),
    }


@router.get("/sessions")
async def get_sessions() -> List[Dict[str, Any]]:
    """Get list of all workflow sessions."""
    sessions = [
        {
            "session_id": session["session_id"],
            "transcript": session["transcript"],
            "timestamp": session["timestamp"],
            "status": session["status"],
        }
        for session in sorted(
            workflow_sessions.values(), 
            key=lambda x: x["timestamp"], 
            reverse=True
        )
    ]
    return sessions[:50]  # Return last 50 sessions


@router.get("/{session_id}")
async def get_workflow(session_id: str) -> Dict[str, Any]:
    """Get workflow details for a specific session."""
    if session_id not in workflow_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return workflow_sessions[session_id]


@router.get("/viewer/ui")
async def get_viewer_ui():
    """Serve the workflow viewer HTML page."""
    html_path = os.path.join("static", "workflow_viewer.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Viewer UI not found")
    return FileResponse(html_path)


@router.get("/viewer/flow")
async def get_flow_viewer_ui():
    """Serve the modern flow-based workflow viewer HTML page."""
    html_path = os.path.join("static", "workflow_flow_viewer.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Flow viewer UI not found")
    return FileResponse(html_path)


@router.get("/viewer/visual")
async def get_visual_flow_viewer_ui():
    """Serve the visual flow viewer with connected agents and wires."""
    html_path = os.path.join("static", "workflow_visual_flow.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Visual flow viewer UI not found")
    return FileResponse(html_path)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a workflow session."""
    if session_id in workflow_sessions:
        del workflow_sessions[session_id]
        return {"message": "Session deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/sessions/all")
async def clear_all_sessions():
    """Clear all workflow sessions."""
    workflow_sessions.clear()
    return {"message": "All sessions cleared"}
