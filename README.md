# Example Receiver Service

A reference implementation of a message consumer service for HomeHelper that demonstrates Redis event subscription, file-based data persistence, and REST API integration.

## Purpose

This service serves as the "receiver" in a sender/receiver demo pair, demonstrating the subscriber side of Redis-based inter-app communication in the HomeHelper ecosystem. It validates HomeHelper's core functionality for service apps, particularly:

- Redis event subscription
- File-based data persistence with rotation
- REST API for data browsing
- Health monitoring
- Data directory management

## How It Works

The service:
1. Subscribes to `example.message.sent` events published by the Example Sender Service
2. Validates incoming messages
3. Writes messages to text files in the data directory
4. Rotates files every 10 messages
5. Exposes REST API endpoints for browsing saved messages
6. Reports health status and metrics

## Relationship to Example Sender Service

This receiver works in tandem with the Example Sender Service:
- **Sender**: Publishes messages to Redis every 30 seconds
- **Receiver**: Subscribes to those messages and persists them to files

Together, they demonstrate a complete pub/sub flow in HomeHelper.

## Quick Start

### Prerequisites

- Python 3.8+
- Redis server running
- pip for installing dependencies

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
# Start Redis (if not already running)
redis-server

# Run the service
python app.py --port 8200 --redis-url redis://localhost:6379 --data-dir ./test_data --logs-dir ./test_logs
```

### Testing with Manual Messages

```bash
# Publish a test message
redis-cli PUBLISH homehelper:events:example.message.sent '{"source":"test","event_type":"example.message.sent","timestamp":1704067200,"data":{"message_number":1,"content":"Test message"}}'

# Check the file was created
cat ./test_data/example_receiver/messages/messages_batch_0001.txt
```

## Expected Behavior

### File Rotation

- Messages are written to files in `{data_dir}/example_receiver/messages/`
- Each file contains exactly 10 messages
- Files are named `messages_batch_0001.txt`, `messages_batch_0002.txt`, etc.
- After the 10th message, the current file is closed and a new one is created
- Batch numbering continues across service restarts

### File Format

Each line in a message file follows this format:

```
[2024-01-01 10:30:00] Message #1: this is Message N° 1 being posted into Redis at 2024-01-01 10:30
[2024-01-01 10:30:30] Message #2: this is Message N° 2 being posted into Redis at 2024-01-01 10:31
```

## API Endpoints

### Health Check

```bash
curl http://localhost:8200/health | jq
```

**Response:**
```json
{
  "health": "good",
  "message": "Receiver service running normally",
  "extra_info": {
    "total_messages_received": 25,
    "current_batch_number": 3,
    "messages_in_current_batch": 5,
    "total_files": 2,
    "last_message_received": "2024-01-01 10:35:00",
    "redis_connected": true
  }
}
```

**Health Status Values:**
- `"good"`: Redis connected, messages being received
- `"warning"`: Redis connection issues OR no messages in 5+ minutes
- `"error"`: Critical failure

### UI Resources

```bash
curl http://localhost:8200/ui
```

**Response:**
```json
["files"]
```

### List All Files

```bash
curl http://localhost:8200/api/files | jq
```

**Response:**
```json
[
  {
    "id": 1,
    "filename": "messages_batch_0001.txt",
    "message_count": 10,
    "file_size_bytes": 1234,
    "date_created": 1704067200,
    "date_modified": 1704067500
  },
  {
    "id": 2,
    "filename": "messages_batch_0002.txt",
    "message_count": 10,
    "file_size_bytes": 1256,
    "date_created": 1704067800,
    "date_modified": 1704068100
  }
]
```

### Get Single File

```bash
curl http://localhost:8200/api/files/1 | jq
```

**Response:**
```json
{
  "id": 1,
  "filename": "messages_batch_0001.txt",
  "message_count": 10,
  "file_size_bytes": 1234,
  "date_created": 1704067200,
  "date_modified": 1704067500,
  "content": "[2024-01-01 10:30:00] Message #1: ...\n[2024-01-01 10:30:30] Message #2: ...\n",
  "first_message_number": 1,
  "last_message_number": 10
}
```

**Error Response (404):**
```json
{
  "detail": "File with id 99 not found. It may not exist yet."
}
```

## Testing

### Verify Service is Running

```bash
# Check health
curl http://localhost:8200/health

# Should return health status with "good" or "warning"
```

### Test Message Reception

```bash
# Publish test messages
for i in {1..15}; do
  redis-cli PUBLISH homehelper:events:example.message.sent "{\"source\":\"test\",\"event_type\":\"example.message.sent\",\"timestamp\":$(date +%s),\"data\":{\"message_number\":$i,\"content\":\"Test message $i\"}}"
  sleep 1
done

# Verify files were created
ls -la ./test_data/example_receiver/messages/

# Should see:
# messages_batch_0001.txt (10 messages)
# messages_batch_0002.txt (5 messages)
```

### Test API Endpoints

```bash
# List files
curl http://localhost:8200/api/files | jq

# Get first file
curl http://localhost:8200/api/files/1 | jq

# Try non-existent file (should return 404)
curl http://localhost:8200/api/files/999
```

### Test Invalid Messages

```bash
# Publish invalid message (missing fields)
redis-cli PUBLISH homehelper:events:example.message.sent '{"invalid":"message"}'

# Check logs - should see warning but service continues
tail -f ./test_logs/example_receiver/app_*.log
```

### Test Service Restart

```bash
# Stop service (Ctrl+C)
# Restart service
python app.py --port 8200 --redis-url redis://localhost:6379 --data-dir ./test_data --logs-dir ./test_logs

# Verify batch numbering continues correctly
# Check logs for "Resuming from batch X"
```

## Troubleshooting

### Service won't start

**Problem**: `Address already in use`
**Solution**: Change the port or kill the process using port 8200

```bash
lsof -ti:8200 | xargs kill -9
```

### Redis connection failed

**Problem**: `Failed to connect to Redis`
**Solution**: Ensure Redis is running

```bash
# Start Redis
redis-server

# Test connection
redis-cli ping
# Should return: PONG
```

### No messages being received

**Problem**: Service running but no files created
**Solution**: 
1. Check Redis is running
2. Verify sender service is publishing messages
3. Check logs for errors

```bash
tail -f ./test_logs/example_receiver/app_*.log
```

### Files not rotating

**Problem**: File has more than 10 messages
**Solution**: This shouldn't happen. Check logs for errors during file write.

### Permission denied on directories

**Problem**: Cannot create data or log directories
**Solution**: Use directories where you have write permissions or run with appropriate permissions

```bash
# Create directories with proper permissions
mkdir -p ./test_data ./test_logs
chmod 755 ./test_data ./test_logs
```

## Known Limitations

### File Accumulation

Files accumulate indefinitely with no automatic cleanup. This is intentional for the demo.

**Impact**: After extended operation, disk space may fill up.

**Analysis**: 
- 1 message every 30 seconds = 2,880 messages/day
- ~288 files/day (10 messages per file)
- After 1 year = ~105 MB, ~105,000 files

**Mitigation**: Real applications should implement retention policies. For this demo, manually delete old files if needed.

### No Message Buffering

If Redis goes down, messages published during the outage are lost. This is by design.

**Reason**: Redis pub/sub is fire-and-forget. The demo shouldn't hide this behavior. Real applications requiring reliability should use Redis Streams.

### Batch Number Overflow

Using 4-digit zero-padding supports max 9999 batches (99,990 messages).

**Impact**: After ~34 days of continuous operation (at 1 msg/30s), filenames will have 5 digits instead of 4.

**Mitigation**: Files remain readable and sortable. This is acceptable for a demo.

### No Partial Batch Recovery

If the service crashes mid-batch, the incomplete batch file remains.

**Impact**: Last file may have fewer than 10 messages.

**Mitigation**: This is acceptable for a demo. Real applications should implement recovery logic.

## Integration with HomeHelper

When installed in HomeHelper, the service:

1. Receives port assignment via `--port` parameter
2. Gets Redis URL via `--redis-url` parameter
3. Stores data in `/opt/homehelper/data/example_receiver/`
4. Writes logs to `/opt/homehelper/logs/example_receiver/`
5. Starts automatically with HomeHelper (if `auto_start: true`)
6. Restarts on failure (per `restart_policy: "always"`)

## Development

### Code Structure

- **Argument parsing**: Command-line arguments
- **Logging setup**: File and console logging
- **Global state**: Counters, locks, file handles
- **Data directory setup**: Create and manage directories
- **Redis connection**: Connect and ping Redis
- **Message validation**: Validate event structure
- **File operations**: Write and rotate files
- **Redis subscriber**: Background thread for events
- **File scanning**: Build file metadata
- **FastAPI endpoints**: REST API handlers
- **Shutdown handling**: Graceful cleanup

### Key Functions

- `validate_message(event)`: Validates message structure
- `write_message(content)`: Writes message with rotation
- `message_subscriber()`: Background thread for Redis
- `scan_message_files()`: Scans directory for metadata
- `health()`: Health check endpoint
- `get_files()`: List files endpoint
- `get_file(id)`: Single file endpoint

## License

This is a demo application for HomeHelper. Use as a reference for building your own services.
