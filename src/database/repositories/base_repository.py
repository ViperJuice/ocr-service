"""Base repository with common CRUD operations."""
from typing import Any, Dict, List, Optional
from supabase import Client
from postgrest import APIError
import logging

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, client: Client, table_name: str):
        """Initialize base repository.

        Args:
            client: Supabase client instance
            table_name: Name of the database table
        """
        self.client = client
        self.table_name = table_name

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record.

        Args:
            data: Record data as dictionary

        Returns:
            Created record with generated fields

        Raises:
            APIError: If database operation fails
        """
        try:
            result = self.client.table(self.table_name).insert(data).execute()
            return result.data[0] if result.data else None
        except APIError as e:
            logger.error(f"Error creating record in {self.table_name}: {e}")
            raise

    async def get_by_id(self, id_column: str, id_value: str) -> Optional[Dict[str, Any]]:
        """Get a record by ID.

        Args:
            id_column: Name of the ID column
            id_value: Value of the ID

        Returns:
            Record dict or None if not found
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq(id_column, id_value)
                .execute()
            )
            return result.data[0] if result.data else None
        except APIError as e:
            logger.error(f"Error getting record from {self.table_name}: {e}")
            raise

    async def update(
        self, id_column: str, id_value: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a record.

        Args:
            id_column: Name of the ID column
            id_value: Value of the ID
            data: Fields to update

        Returns:
            Updated record or None
        """
        try:
            result = (
                self.client.table(self.table_name)
                .update(data)
                .eq(id_column, id_value)
                .execute()
            )
            return result.data[0] if result.data else None
        except APIError as e:
            logger.error(f"Error updating record in {self.table_name}: {e}")
            raise

    async def delete(self, id_column: str, id_value: str) -> bool:
        """Delete a record.

        Args:
            id_column: Name of the ID column
            id_value: Value of the ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            result = (
                self.client.table(self.table_name)
                .delete()
                .eq(id_column, id_value)
                .execute()
            )
            return len(result.data) > 0
        except APIError as e:
            logger.error(f"Error deleting record from {self.table_name}: {e}")
            raise

    async def list_all(
        self, filters: Optional[Dict[str, Any]] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List records with optional filters.

        Args:
            filters: Optional dictionary of column:value filters
            limit: Maximum number of records to return

        Returns:
            List of records
        """
        try:
            query = self.client.table(self.table_name).select("*")

            if filters:
                for column, value in filters.items():
                    query = query.eq(column, value)

            result = query.limit(limit).execute()
            return result.data
        except APIError as e:
            logger.error(f"Error listing records from {self.table_name}: {e}")
            raise
