"""
Enhanced logging configuration with improved readability.

Features:
- Color-coded log levels
- Visual grouping of related operations
- Cleaner module names
- Phase/section markers
"""

import contextvars
import logging
import sys
import uuid
from typing import Optional

from config.settings import Settings

# Request ID context variable
request_id_var = contextvars.ContextVar("request_id", default="no-request-id")

# Custom TRACE level
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def trace(self, message, *args, **kwargs):
    """Log a message with severity 'TRACE'."""
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


logging.Logger.trace = trace


class RequestIDFilter(logging.Filter):
    """Inject request ID into log records."""
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


# ANSI color codes for Windows terminal
class Colors:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Log level colors
    DEBUG = "\033[36m"      # Cyan
    INFO = "\033[32m"       # Green
    WARNING = "\033[33m"    # Yellow
    ERROR = "\033[31m"      # Red
    CRITICAL = "\033[35m"   # Magenta
    
    # Component colors
    GRAPH = "\033[94m"      # Light Blue
    AGENT = "\033[95m"      # Light Magenta
    SERVICE = "\033[96m"    # Light Cyan
    API = "\033[93m"        # Light Yellow


# Module name mappings for cleaner output
MODULE_SHORT_NAMES = {
    "aura_graph.graph": "GRAPH",
    "aura_graph.nodes": "NODE",
    "aura_graph.edges": "EDGE",
    "perception_node": "PERCEPT",
    "agents.commander": "CMDR",
    "agents.navigator": "NAV",
    "agents.responder": "RESP",
    "agents.screen_reader": "SCREEN",
    "agents.validator": "VALID",
    "services.llm": "LLM",
    "services.vlm": "VLM",
    "services.stt": "STT",
    "services.tts": "TTS",
    "services.perception_controller": "PERCEPT",
    "services.screenshot_service": "SCREENSHOT",
    "services.ui_tree_service": "UITREE",
    "services.real_device_executor": "EXEC",
    "api_handlers.websocket_router": "WS",
    "api_handlers.task_router": "API",
    "perception.selectors": "SELECT",
    "perception.validators": "PVALID",
}

# Phase markers for visual grouping
PHASE_MARKERS = {
    "STT": "🎤 SPEECH",
    "INTENT": "🧠 INTENT",
    "PERCEPT": "👁️ PERCEPTION",
    "PLAN": "📋 PLANNING", 
    "EXEC": "⚡ EXECUTION",
    "SPEAK": "🔊 RESPONSE",
}


class EnhancedHandler(logging.StreamHandler):
    """Enhanced logging handler with colors and better formatting."""
    
    def __init__(self):
        super().__init__(sys.stdout)
        # Enable ANSI colors on Windows
        if sys.platform == "win32":
            import os
            os.system("")  # Enable ANSI escape sequences
    
    def _get_level_color(self, levelname: str) -> str:
        """Get color for log level."""
        colors = {
            "DEBUG": Colors.DEBUG,
            "INFO": Colors.INFO,
            "WARNING": Colors.WARNING,
            "ERROR": Colors.ERROR,
            "CRITICAL": Colors.CRITICAL,
        }
        return colors.get(levelname, Colors.RESET)
    
    def _get_short_module(self, name: str) -> str:
        """Get shortened module name."""
        # Check direct mapping
        if name in MODULE_SHORT_NAMES:
            return MODULE_SHORT_NAMES[name]
        
        # Check partial matches
        for full_name, short_name in MODULE_SHORT_NAMES.items():
            if name.endswith(full_name) or full_name in name:
                return short_name
        
        # Fallback: use last part of module name
        parts = name.split(".")
        return parts[-1].upper()[:8]
    
    def _clean_message(self, msg: str) -> str:
        """Clean up message - keep useful emojis, remove clutter."""
        # Keep phase-relevant emojis, remove decorative ones
        decorative_emojis = ["✅", "❌", "⚠️", "🎯", "📤", "📥", "🔄", "📊", "🔇",
                           "🎵", "▶️", "🚫", "📷", "🎨", "🎭", "📝", "🔐", "📺",
                           "🖼️", "🚀", "🔌", "🤔"]
        for emoji in decorative_emojis:
            msg = msg.replace(emoji, "")
        
        # Clean up extra spaces
        msg = " ".join(msg.split()).strip()
        return msg
    
    def emit(self, record):
        """Emit log record with enhanced formatting."""
        try:
            # Get components
            level_color = self._get_level_color(record.levelname)
            short_module = self._get_short_module(record.name)
            msg = self._clean_message(str(record.msg))
            
            # Skip empty messages
            if not msg:
                return
            
            # Format timestamp (shorter)
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Build formatted line
            # Format: HH:MM:SS │ LEVEL │ MODULE │ Message
            level_str = f"{level_color}{record.levelname:<5}{Colors.RESET}"
            module_str = f"{Colors.DIM}{short_module:<8}{Colors.RESET}"
            
            # Add visual separator for important transitions
            prefix = ""
            msg_lower = msg.lower()
            
            # Detect phase transitions
            if "streaming task" in msg_lower and "executing" in msg_lower:
                prefix = f"\n{Colors.BOLD}{'─' * 60}{Colors.RESET}\n{Colors.GRAPH}▶ NEW REQUEST{Colors.RESET}\n"
            elif "task completed" in msg_lower:
                prefix = f"{Colors.GRAPH}✓ COMPLETED{Colors.RESET} "
            elif "intent parsed" in msg_lower or "normalized intent" in msg_lower:
                prefix = f"{Colors.AGENT}→ {Colors.RESET}"
            elif "perception complete" in msg_lower:
                prefix = f"{Colors.SERVICE}◉ {Colors.RESET}"
            elif "routing to" in msg_lower:
                prefix = f"{Colors.DIM}  ↳ {Colors.RESET}"
            
            # Highlight errors
            if record.levelname == "ERROR":
                msg = f"{Colors.ERROR}{msg}{Colors.RESET}"
            elif record.levelname == "WARNING":
                msg = f"{Colors.WARNING}{msg}{Colors.RESET}"
            
            formatted = f"{Colors.DIM}{timestamp}{Colors.RESET} │ {level_str} │ {module_str} │ {prefix}{msg}"
            
            print(formatted, file=self.stream)
            self.stream.flush()
            
        except Exception:
            # Fallback to basic output
            super().emit(record)


class SimpleHandler(logging.StreamHandler):
    """Simple handler for non-TTY environments."""
    
    def emit(self, record):
        """Emit log record in structured format."""
        msg = str(record.msg)
        
        # Remove emojis
        emojis = ["✅", "❌", "⚠️", "🎯", "🤖", "📋", "💬", "🔍", "📱", 
                  "🔊", "⚡", "📸", "📤", "📥", "🔄", "📊", "🔇", "🎤", 
                  "🎵", "▶️", "🚫", "📷", "🎨", "🎭", "📝", "🔐", "📺",
                  "🖼️", "🚀", "🔌", "🤔", "👁️", "🧠"]
        for emoji in emojis:
            msg = msg.replace(emoji, "")
        
        msg = " ".join(msg.split()).strip()
        record.msg = msg
        super().emit(record)


def setup_logger(
    name: str = "aura", level: Optional[str] = None
) -> logging.Logger:
    """
    Set up enhanced logger with colors and better formatting.

    Args:
        name: Logger name (typically module name)
        level: Logging level override

    Returns:
        Configured logger
    """
    try:
        settings = Settings()
        log_level = level or settings.log_level
    except Exception:
        log_level = "INFO"

    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if not logger.handlers:
        # Set logger level
        if log_level.upper() == "TRACE":
            logger.setLevel(TRACE_LEVEL)
        else:
            logger.setLevel(getattr(logging, log_level.upper()))

        # Use enhanced handler if TTY, simple otherwise
        if sys.stdout.isatty():
            handler = EnhancedHandler()
        else:
            handler = SimpleHandler()
            format_string = "[%(asctime)s] %(levelname)-5s [%(name)s] %(message)s"
            formatter = logging.Formatter(format_string, datefmt="%H:%M:%S")
            handler.setFormatter(formatter)

        # Set handler level
        if log_level.upper() == "TRACE":
            handler.setLevel(TRACE_LEVEL)
        else:
            handler.setLevel(getattr(logging, log_level.upper()))

        # Add request ID filter
        handler.addFilter(RequestIDFilter())

        logger.addHandler(handler)
        logger.propagate = False

    return logger


def set_request_id(request_id: str = None) -> str:
    """Set request ID for current context."""
    if not request_id:
        request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)
    return request_id


def get_request_id() -> str:
    """Get current request ID."""
    return request_id_var.get()


def get_logger(name: str = "aura") -> logging.Logger:
    """
    Get a logger instance with enhanced formatting.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger
    """
    return setup_logger(name)


# Default logger
logger = get_logger()


def log_agent_output(agent_name: str, output: str, provider: str = None, model: str = None):
    """
    Print agent output in a CrewAI-style box format to the terminal.
    
    Args:
        agent_name: Name of the agent (e.g., "Navigator", "Planner")
        output: The agent's response/output text
        provider: Optional LLM provider name
        model: Optional model name
    """
    # Box characters
    TOP_LEFT = "┏"
    TOP_RIGHT = "┓"
    BOTTOM_LEFT = "┗"
    BOTTOM_RIGHT = "┛"
    HORIZONTAL = "━"
    VERTICAL = "┃"
    
    # Colors
    AGENT_COLOR = Colors.AGENT  # Light Magenta
    RESET = Colors.RESET
    DIM = Colors.DIM
    
    # Box width
    BOX_WIDTH = 76
    
    # Build header
    agent_header = f" 🤖 {agent_name.upper()} "
    if provider and model:
        agent_header += f"({provider}/{model}) "
    
    # Calculate padding
    header_padding = BOX_WIDTH - len(agent_header) - 2
    if header_padding < 0:
        header_padding = 0
    
    # Print top border with agent name
    print(f"{AGENT_COLOR}{TOP_LEFT}{HORIZONTAL}{agent_header}{HORIZONTAL * header_padding}{TOP_RIGHT}{RESET}")
    
    # Print output lines
    lines = output.split('\n')
    for line in lines[:30]:  # Limit to 30 lines
        # Truncate long lines
        display_line = line[:BOX_WIDTH - 4] if len(line) > BOX_WIDTH - 4 else line
        padding = BOX_WIDTH - len(display_line) - 2
        print(f"{AGENT_COLOR}{VERTICAL}{RESET} {display_line}{' ' * padding}{AGENT_COLOR}{VERTICAL}{RESET}")
    
    if len(lines) > 30:
        more_msg = f"... ({len(lines) - 30} more lines)"
        padding = BOX_WIDTH - len(more_msg) - 2
        print(f"{AGENT_COLOR}{VERTICAL}{RESET} {DIM}{more_msg}{RESET}{' ' * padding}{AGENT_COLOR}{VERTICAL}{RESET}")
    
    # Print bottom border
    print(f"{AGENT_COLOR}{BOTTOM_LEFT}{HORIZONTAL * BOX_WIDTH}{BOTTOM_RIGHT}{RESET}")
