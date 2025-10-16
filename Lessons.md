# Lessons Learned

This file tracks fixes made and corrections received during development.

---

## Project: Example Receiver Service (P-001)

### Date: 2025-10-16

#### File Rotation Logic
- **Lesson**: File rotation should happen AFTER writing the 10th message, not before. The current file is closed after reaching 10 messages, and the next file is created when the 11th message arrives.
- **Implementation**: Used a counter that increments after each write, then checks if it reached 10 to trigger rotation.

#### Batch Numbering Persistence
- **Lesson**: When restarting the service, need to scan existing files to determine the correct batch number to continue from.
- **Implementation**: Added logic to scan for existing files on startup and resume from the last batch number, accounting for incomplete batches.

#### Thread Safety
- **Lesson**: File operations need to be protected with locks when accessed from both the subscriber thread and API endpoints.
- **Implementation**: Used `threading.Lock()` to protect file write operations and file reading in API endpoints.

#### Message Validation
- **Lesson**: Invalid messages should be logged but not crash the service. The subscriber should continue processing subsequent messages.
- **Implementation**: Wrapped message processing in try-except blocks and logged validation errors as warnings.

#### Health Status Logic
- **Lesson**: Health endpoint should reflect actual service state, including Redis connectivity and recent message activity.
- **Implementation**: Track last message time and Redis connection status to determine health status ("good", "warning", or "error").

#### File Metadata Extraction
- **Lesson**: Parsing message numbers from file content requires careful string manipulation to handle various formats.
- **Implementation**: Used split operations on known patterns ("Message #") to extract first and last message numbers.

---

