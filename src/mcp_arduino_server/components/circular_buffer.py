"""
Enhanced Circular Buffer with Proper Cursor Management
Handles wraparound and cursor invalidation for long-running sessions
"""

import uuid
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum


class SerialDataType(str, Enum):
    """Types of serial data entries"""
    RECEIVED = "received"
    SENT = "sent"
    SYSTEM = "system"
    ERROR = "error"


@dataclass
class SerialDataEntry:
    """A single serial data entry"""
    timestamp: str
    type: SerialDataType
    data: str
    port: str
    index: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CursorState:
    """Tracks cursor position and validity"""
    cursor_id: str
    position: int  # Global index position
    created_at: str
    last_read: Optional[str] = None
    reads_count: int = 0
    is_valid: bool = True  # False if cursor points to overwritten data


class CircularSerialBuffer:
    """
    True circular buffer implementation with robust cursor management

    Features:
    - Fixed memory footprint
    - Automatic cursor invalidation when data is overwritten
    - Efficient O(1) append and pop operations
    - Cursor wraparound support
    """

    def __init__(self, max_size: int = 10000):
        """
        Initialize circular buffer

        Args:
            max_size: Maximum number of entries to store
        """
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)  # Efficient circular buffer
        self.global_index = 0  # Ever-incrementing index
        self.oldest_index = 0  # Index of oldest entry in buffer
        self.cursors: Dict[str, CursorState] = {}

        # Statistics
        self.total_entries = 0
        self.entries_dropped = 0

    def add_entry(self, port: str, data: str, data_type: SerialDataType = SerialDataType.RECEIVED):
        """Add a new entry to the circular buffer"""
        entry = SerialDataEntry(
            timestamp=datetime.now().isoformat(),
            type=data_type,
            data=data,
            port=port,
            index=self.global_index
        )

        # Check if buffer is at capacity
        if len(self.buffer) >= self.max_size:
            # An entry will be dropped
            oldest = self.buffer[0]
            self.oldest_index = self.buffer[1].index if len(self.buffer) > 1 else self.global_index + 1
            self.entries_dropped += 1

            # Invalidate cursors pointing to dropped data
            self._invalidate_stale_cursors(oldest.index)

        # Add new entry (deque handles removal automatically)
        self.buffer.append(entry)
        self.global_index += 1
        self.total_entries += 1

    def _invalidate_stale_cursors(self, dropped_index: int):
        """Invalidate cursors pointing to dropped data"""
        for cursor_id, cursor in self.cursors.items():
            if cursor.position <= dropped_index:
                # This cursor points to data that has been overwritten
                cursor.is_valid = False

    def create_cursor(self, start_from: str = "oldest") -> str:
        """
        Create a new cursor for reading data

        Args:
            start_from: Where to start reading
                - "oldest": Start from oldest available entry
                - "newest": Start from newest entry
                - "next": Start from next entry to be added
                - "beginning": Start from absolute beginning (may be invalid)

        Returns:
            Cursor ID
        """
        cursor_id = str(uuid.uuid4())

        if start_from == "oldest" and self.buffer:
            position = self.buffer[0].index
        elif start_from == "newest" and self.buffer:
            position = self.buffer[-1].index
        elif start_from == "next":
            position = self.global_index
        elif start_from == "beginning":
            position = 0
        else:
            # Default to next entry
            position = self.global_index

        cursor = CursorState(
            cursor_id=cursor_id,
            position=position,
            created_at=datetime.now().isoformat(),
            is_valid=True
        )

        # Check if cursor is already invalid (pointing to dropped data)
        if self.buffer and position < self.buffer[0].index:
            cursor.is_valid = False

        self.cursors[cursor_id] = cursor
        return cursor_id

    def read_from_cursor(
        self,
        cursor_id: str,
        limit: int = 100,
        port_filter: Optional[str] = None,
        type_filter: Optional[SerialDataType] = None,
        auto_recover: bool = True
    ) -> dict:
        """
        Read entries from cursor position

        Args:
            cursor_id: Cursor to read from
            limit: Maximum entries to return
            port_filter: Filter by port
            type_filter: Filter by data type
            auto_recover: If cursor is invalid, automatically recover from oldest

        Returns:
            Dictionary with entries, cursor state, and metadata
        """
        if cursor_id not in self.cursors:
            return {
                "success": False,
                "error": "Cursor not found",
                "entries": [],
                "has_more": False
            }

        cursor = self.cursors[cursor_id]

        # Handle invalid cursor
        if not cursor.is_valid:
            if auto_recover and self.buffer:
                # Recover by jumping to oldest available data
                cursor.position = self.buffer[0].index
                cursor.is_valid = True
                warning = "Cursor recovered - some data was missed due to buffer overflow"
            else:
                return {
                    "success": False,
                    "error": "Cursor invalid - data has been overwritten",
                    "entries": [],
                    "has_more": False,
                    "cursor_invalid": True,
                    "suggested_action": "Create new cursor with start_from='oldest'"
                }
        else:
            warning = None

        entries = []
        last_index = cursor.position

        for entry in self.buffer:
            # Skip entries before cursor
            if entry.index < cursor.position:
                continue

            # Apply filters
            if port_filter and entry.port != port_filter:
                continue
            if type_filter and entry.type != type_filter:
                continue

            entries.append(entry)
            last_index = entry.index

            if len(entries) >= limit:
                break

        # Update cursor position and stats
        if entries:
            cursor.position = last_index + 1
            cursor.last_read = datetime.now().isoformat()
            cursor.reads_count += 1

        # Check if there's more data
        has_more = False
        if self.buffer and cursor.position <= self.buffer[-1].index:
            # There are unread entries
            has_more = True

        result = {
            "success": True,
            "cursor_id": cursor_id,
            "entries": [e.to_dict() for e in entries],
            "count": len(entries),
            "has_more": has_more,
            "cursor_state": {
                "position": cursor.position,
                "is_valid": cursor.is_valid,
                "reads_count": cursor.reads_count,
                "created_at": cursor.created_at,
                "last_read": cursor.last_read
            },
            "buffer_state": {
                "size": len(self.buffer),
                "max_size": self.max_size,
                "oldest_index": self.buffer[0].index if self.buffer else None,
                "newest_index": self.buffer[-1].index if self.buffer else None,
                "total_entries": self.total_entries,
                "entries_dropped": self.entries_dropped
            }
        }

        if warning:
            result["warning"] = warning

        return result

    def delete_cursor(self, cursor_id: str) -> bool:
        """Delete a cursor"""
        if cursor_id in self.cursors:
            del self.cursors[cursor_id]
            return True
        return False

    def get_cursor_info(self, cursor_id: str) -> Optional[dict]:
        """Get information about a cursor"""
        if cursor_id not in self.cursors:
            return None

        cursor = self.cursors[cursor_id]
        return {
            "cursor_id": cursor_id,
            "position": cursor.position,
            "is_valid": cursor.is_valid,
            "created_at": cursor.created_at,
            "last_read": cursor.last_read,
            "reads_count": cursor.reads_count,
            "entries_behind": cursor.position - self.buffer[0].index if self.buffer and cursor.is_valid else None,
            "entries_ahead": self.buffer[-1].index - cursor.position + 1 if self.buffer and cursor.is_valid else None
        }

    def list_cursors(self) -> List[dict]:
        """List all active cursors"""
        return [self.get_cursor_info(cursor_id) for cursor_id in self.cursors]

    def get_latest(self, port: Optional[str] = None, limit: int = 10) -> List[SerialDataEntry]:
        """Get latest entries without cursor"""
        if not self.buffer:
            return []

        # Get from the end of buffer
        entries = list(self.buffer)[-limit:] if not port else [
            e for e in self.buffer if e.port == port
        ][-limit:]

        return entries

    def clear(self, port: Optional[str] = None):
        """Clear buffer for a specific port or all"""
        if port:
            # Filter out entries for specified port
            self.buffer = deque(
                [e for e in self.buffer if e.port != port],
                maxlen=self.max_size
            )
            # Update oldest_index if buffer not empty
            if self.buffer:
                self.oldest_index = self.buffer[0].index
        else:
            # Clear entire buffer
            self.buffer.clear()
            self.entries_dropped = 0
            # Don't reset global_index to maintain continuity

        # Invalidate all cursors when clearing
        for cursor in self.cursors.values():
            cursor.is_valid = False

    def get_statistics(self) -> dict:
        """Get buffer statistics"""
        return {
            "buffer_size": len(self.buffer),
            "max_size": self.max_size,
            "usage_percent": (len(self.buffer) / self.max_size) * 100,
            "total_entries": self.total_entries,
            "entries_dropped": self.entries_dropped,
            "drop_rate": (self.entries_dropped / self.total_entries * 100) if self.total_entries > 0 else 0,
            "oldest_index": self.buffer[0].index if self.buffer else None,
            "newest_index": self.buffer[-1].index if self.buffer else None,
            "active_cursors": len(self.cursors),
            "valid_cursors": sum(1 for c in self.cursors.values() if c.is_valid),
            "invalid_cursors": sum(1 for c in self.cursors.values() if not c.is_valid)
        }

    def cleanup_invalid_cursors(self) -> int:
        """Remove all invalid cursors and return count removed"""
        invalid = [cid for cid, cursor in self.cursors.items() if not cursor.is_valid]
        for cursor_id in invalid:
            del self.cursors[cursor_id]
        return len(invalid)

    def resize_buffer(self, new_size: int) -> dict:
        """
        Resize the buffer (may cause data loss if shrinking)

        Returns:
            Statistics about the resize operation
        """
        old_size = self.max_size
        old_len = len(self.buffer)

        if new_size < old_len:
            # Shrinking - will lose oldest data
            entries_to_drop = old_len - new_size
            dropped_indices = [self.buffer[i].index for i in range(entries_to_drop)]

            # Invalidate affected cursors
            for idx in dropped_indices:
                self._invalidate_stale_cursors(idx)

            self.entries_dropped += entries_to_drop

        # Resize the deque
        new_buffer = deque(self.buffer, maxlen=new_size)
        self.buffer = new_buffer
        self.max_size = new_size

        # Update oldest index
        if self.buffer:
            self.oldest_index = self.buffer[0].index

        return {
            "old_size": old_size,
            "new_size": new_size,
            "entries_before": old_len,
            "entries_after": len(self.buffer),
            "entries_dropped": max(0, old_len - len(self.buffer))
        }