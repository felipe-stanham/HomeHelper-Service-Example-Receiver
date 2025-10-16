"""
Example Receiver Service for HomeHelper
Subscribes to Redis events and writes messages to rotating files
"""

import argparse
import json
import logging
import threading
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import redis
import uvicorn


# ============================================================================
# ARGUMENT PARSING
# ============================================================================

parser = argparse.ArgumentParser(description='Example Receiver Service')
parser.add_argument('--port', type=int, required=True, help='Port to run the service on')
parser.add_argument('--redis-url', type=str, required=False, help='Redis connection URL')
parser.add_argument('--data-dir', type=str, required=False, help='Data directory path')
parser.add_argument('--logs-dir', type=str, required=False, help='Logs directory path')
args = parser.parse_args()


# ============================================================================
# LOGGING SETUP
# ============================================================================

if args.logs_dir:
    logs_dir = Path(args.logs_dir) / "example_receiver"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)


# ============================================================================
# GLOBAL STATE
# ============================================================================

# Counters and state
total_messages_received = 0
current_batch_number = 1
messages_in_current_batch = 0
current_file = None
last_message_time = None
redis_connected = False

# Thread synchronization
file_lock = threading.Lock()
shutdown_event = threading.Event()


# ============================================================================
# DATA DIRECTORY SETUP
# ============================================================================

data_dir = None
messages_dir = None

if args.data_dir:
    data_dir = Path(args.data_dir) / "example_receiver"
    messages_dir = data_dir / "messages"
    messages_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Messages directory: {messages_dir}")
    
    # Check for existing files to continue batch numbering
    if messages_dir.exists():
        existing_files = sorted(messages_dir.glob("messages_batch_*.txt"))
        if existing_files:
            last_file = existing_files[-1]
            # Extract batch number from filename
            batch_num = int(last_file.stem.split('_')[-1])
            # Count messages in last file
            with open(last_file, 'r') as f:
                msg_count = sum(1 for _ in f)
            
            if msg_count >= 10:
                # Last file is complete, start new batch
                current_batch_number = batch_num + 1
                messages_in_current_batch = 0
            else:
                # Last file is incomplete, continue it
                current_batch_number = batch_num
                messages_in_current_batch = msg_count
            
            logger.info(f"Resuming from batch {current_batch_number}, {messages_in_current_batch} messages in current batch")


# ============================================================================
# REDIS CONNECTION SETUP
# ============================================================================

redis_client = None

if args.redis_url:
    try:
        redis_client = redis.from_url(args.redis_url)
        redis_client.ping()
        redis_connected = True
        logger.info(f"Connected to Redis: {args.redis_url}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_connected = False
else:
    logger.warning("No Redis URL provided, event subscription disabled")


# ============================================================================
# MESSAGE VALIDATION
# ============================================================================

def validate_message(event: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate incoming message structure.
    
    Args:
        event: Event dictionary from Redis
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check top-level fields
        if not isinstance(event, dict):
            return False, "Event is not a dictionary"
        
        if event.get('event_type') != 'example.message.sent':
            return False, f"Unexpected event type: {event.get('event_type')}"
        
        if 'data' not in event:
            return False, "Missing 'data' field"
        
        data = event['data']
        
        # Check required data fields
        if 'message_number' not in data:
            return False, "Missing 'message_number' in data"
        
        if 'content' not in data:
            return False, "Missing 'content' in data"
        
        if not isinstance(data['message_number'], int):
            return False, "message_number must be integer"
        
        if not isinstance(data['content'], str):
            return False, "content must be string"
        
        return True, None
        
    except Exception as e:
        return False, f"Validation error: {str(e)}"


# ============================================================================
# FILE WRITING AND ROTATION
# ============================================================================

def write_message(content: str) -> None:
    """
    Write message to current batch file with rotation logic.
    
    Args:
        content: Message content to write
    """
    global current_batch_number, messages_in_current_batch, current_file, total_messages_received
    
    if not messages_dir:
        logger.error("Messages directory not configured")
        return
    
    with file_lock:
        # Open file if needed
        if current_file is None:
            filename = f"messages_batch_{current_batch_number:04d}.txt"
            filepath = messages_dir / filename
            current_file = open(filepath, 'a')
            logger.info(f"Opened file: {filename}")
        
        # Format and write message
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}] {content}\n"
        current_file.write(line)
        current_file.flush()  # Ensure immediate write
        
        messages_in_current_batch += 1
        total_messages_received += 1
        
        # Check if rotation needed
        if messages_in_current_batch >= 10:
            current_file.close()
            logger.info(f"Completed batch {current_batch_number} with 10 messages")
            current_file = None
            current_batch_number += 1
            messages_in_current_batch = 0


# ============================================================================
# REDIS SUBSCRIBER
# ============================================================================

def message_subscriber() -> None:
    """
    Background thread that subscribes to Redis events and processes messages.
    """
    global last_message_time, redis_connected
    
    if not redis_client:
        logger.error("Redis client not initialized")
        return
    
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe("homehelper:events:example.message.sent")
        logger.info("Started subscribing to example.message.sent events")
        redis_connected = True
        
        for message in pubsub.listen():
            if shutdown_event.is_set():
                break
                
            if message['type'] == 'message':
                try:
                    # Parse JSON
                    event = json.loads(message['data'])
                    
                    # Validate
                    is_valid, error = validate_message(event)
                    if not is_valid:
                        logger.warning(f"Invalid message: {error}")
                        continue
                    
                    # Extract content
                    message_number = event['data']['message_number']
                    content = event['data']['content']
                    
                    # Write to file
                    write_message(f"Message #{message_number}: {content}")
                    
                    # Update last message time
                    last_message_time = datetime.now()
                    
                    logger.info(f"Received and saved message #{message_number}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message JSON: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        pubsub.close()
        logger.info("Subscriber thread stopped")
        
    except Exception as e:
        logger.error(f"Subscriber error: {e}")
        redis_connected = False


# ============================================================================
# FILE SCANNING
# ============================================================================

def scan_message_files() -> List[Dict[str, Any]]:
    """
    Scan data directory and return list of file metadata.
    
    Returns:
        List of file metadata dictionaries
    """
    if not messages_dir or not messages_dir.exists():
        return []
    
    files = []
    for filepath in sorted(messages_dir.glob("messages_batch_*.txt")):
        try:
            # Parse batch number from filename
            batch_num = int(filepath.stem.split('_')[-1])
            
            # Get file stats
            stat = filepath.stat()
            
            # Count lines in file
            with file_lock:
                with open(filepath, 'r') as f:
                    message_count = sum(1 for _ in f)
            
            files.append({
                "id": batch_num,
                "filename": filepath.name,
                "message_count": message_count,
                "file_size_bytes": stat.st_size,
                "date_created": int(stat.st_ctime),
                "date_modified": int(stat.st_mtime)
            })
        except Exception as e:
            logger.error(f"Error scanning file {filepath}: {e}")
    
    return files


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Example Receiver Service")


@app.get("/health")
async def health():
    """
    Health check endpoint (REQUIRED by HomeHelper spec).
    
    Returns service health status and metrics.
    """
    # Determine health status
    health_status = "good"
    health_message = "Receiver service running normally"
    
    # Check for warnings
    if not redis_connected:
        health_status = "warning"
        health_message = "Redis connection issue"
    elif last_message_time:
        time_since_last = (datetime.now() - last_message_time).total_seconds()
        if time_since_last > 300:  # 5 minutes
            health_status = "warning"
            health_message = f"No messages received in {int(time_since_last)} seconds"
    
    # Build extra info
    extra_info = {
        "total_messages_received": total_messages_received,
        "current_batch_number": current_batch_number,
        "messages_in_current_batch": messages_in_current_batch,
        "total_files": len(scan_message_files()),
        "redis_connected": redis_connected
    }
    
    if last_message_time:
        extra_info["last_message_received"] = last_message_time.strftime('%Y-%m-%d %H:%M:%S')
    
    return {
        "health": health_status,
        "message": health_message,
        "extra_info": extra_info
    }


@app.get("/ui")
async def ui():
    """
    UI endpoint (OPTIONAL) - returns list of available resources.
    """
    return ["files"]


@app.get("/api/files")
async def get_files():
    """
    Get list of all message files with metadata.
    
    Returns:
        List of file metadata dictionaries
    """
    return scan_message_files()


@app.get("/api/files/{file_id}")
async def get_file(file_id: int):
    """
    Get detailed information about a specific file including content.
    
    Args:
        file_id: Batch number of the file
        
    Returns:
        File metadata with content
        
    Raises:
        HTTPException: If file not found
    """
    if not messages_dir:
        raise HTTPException(status_code=500, detail="Data directory not configured")
    
    filename = f"messages_batch_{file_id:04d}.txt"
    filepath = messages_dir / filename
    
    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File with id {file_id} not found. It may not exist yet."
        )
    
    try:
        # Get file stats
        stat = filepath.stat()
        
        # Read file content
        with file_lock:
            with open(filepath, 'r') as f:
                content = f.read()
                lines = content.strip().split('\n')
                message_count = len(lines)
        
        # Parse first and last message numbers
        first_msg_num = None
        last_msg_num = None
        
        if lines:
            # Extract message number from first line
            try:
                first_line = lines[0]
                if "Message #" in first_line:
                    first_msg_num = int(first_line.split("Message #")[1].split(":")[0])
            except:
                pass
            
            # Extract message number from last line
            try:
                last_line = lines[-1]
                if "Message #" in last_line:
                    last_msg_num = int(last_line.split("Message #")[1].split(":")[0])
            except:
                pass
        
        return {
            "id": file_id,
            "filename": filename,
            "message_count": message_count,
            "file_size_bytes": stat.st_size,
            "date_created": int(stat.st_ctime),
            "date_modified": int(stat.st_mtime),
            "content": content,
            "first_message_number": first_msg_num,
            "last_message_number": last_msg_num
        }
        
    except Exception as e:
        logger.error(f"Error reading file {filepath}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


# ============================================================================
# SHUTDOWN HANDLING
# ============================================================================

def shutdown_handler(signum, frame):
    """
    Handle graceful shutdown on SIGTERM or SIGINT.
    """
    logger.info("Shutdown signal received, cleaning up...")
    shutdown_event.set()
    
    # Close current file if open
    global current_file
    if current_file:
        with file_lock:
            current_file.close()
            logger.info("Closed current file")
    
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    logger.info(f"Starting Example Receiver Service on port {args.port}")
    logger.info(f"Configuration: redis={bool(redis_client)}, data_dir={bool(data_dir)}, logs_dir={bool(args.logs_dir)}")
    
    # Start Redis subscriber thread if available
    if redis_client:
        subscriber_thread = threading.Thread(target=message_subscriber, daemon=True)
        subscriber_thread.start()
        logger.info("Started Redis subscriber thread")
    
    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
