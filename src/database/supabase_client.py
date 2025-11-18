"""Supabase client initialization and management."""
import os
from typing import Optional
from supabase import create_client, Client, acreate_client, AsyncClient
from postgrest import APIError
import logging

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Wrapper for Supabase client with connection management."""

    def __init__(self, url: str, service_key: str):
        """Initialize Supabase client.

        Args:
            url: Supabase project URL (e.g., http://localhost:54321)
            service_key: Service role key (bypasses RLS for backend operations)
        """
        self.url = url
        self.service_key = service_key
        self._client: Optional[Client] = None
        self._async_client: Optional[AsyncClient] = None

    def connect(self) -> Client:
        """Connect to Supabase and return client.

        Returns:
            Connected Supabase client instance
        """
        if self._client is None:
            logger.info(f"Connecting to Supabase at {self.url}")
            self._client = create_client(self.url, self.service_key)
            logger.info("✅ Supabase client connected")
        return self._client

    async def async_connect(self) -> AsyncClient:
        """Connect to Supabase and return async client.

        Returns:
            Connected Async Supabase client instance
        """
        if self._async_client is None:
            logger.info(f"Connecting async client to Supabase at {self.url}")
            self._async_client = await acreate_client(self.url, self.service_key)
            logger.info("✅ Supabase async client connected")
        return self._async_client

    @property
    def client(self) -> Client:
        """Get connected client (lazy connect).

        Returns:
            Supabase client instance
        """
        if self._client is None:
            return self.connect()
        return self._client

    @property
    async def async_client(self) -> AsyncClient:
        """Get connected async client (lazy connect).

        Returns:
            Async Supabase client instance
        """
        if self._async_client is None:
            return await self.async_connect()
        return self._async_client

    def disconnect(self):
        """Close connection (cleanup on shutdown)."""
        # Supabase Python client doesn't require explicit cleanup,
        # but we track state for testing and lifecycle management
        if self._client:
            logger.info("Disconnecting from Supabase")
            self._client = None
        if self._async_client:
            logger.info("Disconnecting async client from Supabase")
            self._async_client = None


# Global client instance (initialized in main.py lifespan)
_supabase_client: Optional[SupabaseClient] = None


def initialize_supabase(url: str, service_key: str) -> SupabaseClient:
    """Initialize global Supabase client (called once on startup).

    Args:
        url: Supabase project URL
        service_key: Service role key

    Returns:
        Initialized SupabaseClient instance

    Example:
        >>> # In main.py lifespan
        >>> client = initialize_supabase(
        ...     url=settings.supabase_url,
        ...     service_key=settings.supabase_service_role_key
        ... )
    """
    global _supabase_client
    _supabase_client = SupabaseClient(url, service_key)
    _supabase_client.connect()
    return _supabase_client


def get_supabase_client() -> SupabaseClient:
    """Get global Supabase client instance (dependency injection).

    Returns:
        SupabaseClient instance

    Raises:
        RuntimeError: If client not initialized (call initialize_supabase first)

    Example:
        >>> # In repository constructor
        >>> client = get_supabase_client()
        >>> repo = JobRepository(client.client)
    """
    if _supabase_client is None:
        raise RuntimeError(
            "Supabase client not initialized. "
            "Call initialize_supabase() in main.py lifespan first."
        )
    return _supabase_client
