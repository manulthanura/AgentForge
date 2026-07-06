from .in_memory_repo import InMemoryApprovalRepository
from .postgres_approval_repo import PostgresApprovalRepository

__all__ = ["InMemoryApprovalRepository", "PostgresApprovalRepository"]
