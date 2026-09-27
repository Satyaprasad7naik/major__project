# import os
# from typing import List, Dict, Any
# from sqlalchemy import create_engine, text, inspect
# from app.core.config import settings
# from app.core.logger import logger

# class DatabaseService:
#     def __init__(self):
#         self.engine = create_engine(settings.DATABASE_URL)
#         logger.info(f"DatabaseService initialized with engine: {settings.DATABASE_URL.split('///')[-1]}")
#         self.initialize_db()

#     def initialize_db(self):
#         """Initialize database schema if it doesn't exist."""
#         try:
#             inspector = inspect(self.engine)
#             if not inspector.has_table("users"):
#                 print("Initializing database schema...")
#                 self._execute_sql_file(settings.SCHEMA_PATH)
#                 print("Schema initialized.")
#         except Exception as e:
#             print(f"Error initializing database: {e}")

#     def _execute_sql_file(self, file_path: str):
#         """Execute SQL commands from a file."""
#         if not os.path.exists(file_path):
#             # Try to resolve relative to project root if needed
#             file_path = os.path.join(os.getcwd(), file_path)
            
#         if not os.path.exists(file_path):
#             print(f"Schema file not found at: {file_path}")
#             return

#         with open(file_path, 'r', encoding='utf-8') as f:
#             sql_content = f.read()
            
#         # Split by semicolon for SQLite execution
#         # Note: This is a simple split and might fail on complex stored procs, 
#         # but works for standard CREATE TABLE/INSERT statements.
#         statements = sql_content.split(';')
        
#         with self.engine.connect() as conn:
#             # for statement in statements:
#             #     if statement.strip():
#             #         try:
#             #             conn.execute(text(statement))
#             #         except Exception as e:
#             #             print(f"Error executing statement: {statement[:50]}... -> {e}")
#             # conn.commit()
#             try:
#                 # This automatically commits if successful, and rolls back if it fails
#                 with conn.begin():
#                     for statement in statements:
#                         if statement.strip():
#                             conn.execute(text(statement))
#             except Exception as e:
#                 print(f"Database error! Rolled back to prevent corruption: {e}")

#     def execute(self, sql: str) -> List[Dict[str, Any]]:
#         """Execute a raw SQL query and return results as a list of dicts."""
#         logger.info(f"Executing SQL: {sql}")
#         try:
#             with self.engine.connect() as conn:
#                 result = conn.execute(text(sql))
#                 # Check if it's a SELECT query (returns rows)
#                 if result.returns_rows:
#                     data = [dict(row) for row in result.mappings()]
#                     logger.info(f"Execution complete. Returned {len(data)} rows.")
#                     return data
#                 else:
#                     conn.commit()
#                     logger.info(f"Execution complete. Rows affected: {result.rowcount}")
#                     return [{"status": "success", "rows_affected": result.rowcount}]
#         except Exception as e:
#             logger.error(f"DATABASE EXECUTION ERROR: {str(e)} | Query: {sql}")
#             return []

#     def get_schema_info(self) -> List[str]:
#         """Returns a list of 'table.column' strings for all tables in the database."""
#         schema_info = []
#         try:
#             inspector = inspect(self.engine)
#             tables = inspector.get_table_names()
#             for table in tables:
#                 columns = inspector.get_columns(table)
#                 for col in columns:
#                     schema_info.append(f"{table}.{col['name']}")
#             return schema_info
#         except Exception as e:
#             logger.error(f"Error fetching schema info: {e}")
#             return []

# db_service = DatabaseService()
# import os
# from typing import List, Dict, Any
# from sqlalchemy import create_engine, text, inspect
# from app.core.config import settings
# from app.core.logger import logger
import os
from app.core.config import settings
from typing import List, Dict, Any
from sqlalchemy import text
from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from app.core.logger import logger
from sqlalchemy import text, create_engine, inspect

@contextmanager
def atomic_transaction(engine):
    """
    Explicit BEGIN / COMMIT / ROLLBACK boundary. All statements inside
    succeed together or none are applied.
    """
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()
        
        
class DatabaseService:
    def __init__(self):
        # Configure SQLite connection arguments if using SQLite
        connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
        
        self.engine = create_engine(
            settings.DATABASE_URL,
            connect_args=connect_args
        )
        logger.info(f"DatabaseService initialized with engine: {settings.DATABASE_URL.split('///')[-1]}")
        self.initialize_db()

    def initialize_db(self):
        """Initialize database schema if it doesn't exist."""
        try:
            inspector = inspect(self.engine)
            if not inspector.has_table("users"):
                logger.info("Initializing database schema...")
                self._execute_sql_file(settings.SCHEMA_PATH)
                logger.info("Database schema initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")

    # def _execute_sql_file(self, file_path: str):
    #     """
    #     Execute SQL commands from a file within an atomic transaction.
    #     If a single statement fails, the entire transaction rolls back to prevent database corruption.
    #     """
    #     if not os.path.exists(file_path):
    #         # Try to resolve relative to project root if needed
    #         file_path = os.path.join(os.getcwd(), file_path)
            
    #     if not os.path.exists(file_path):
    #         logger.error(f"Schema file not found at: {file_path}")
    #         return

    #     try:
    #         with open(file_path, 'r', encoding='utf-8') as f:
    #             sql_content = f.read()
                
    #         statements = sql_content.split(';')
            
    #         with self.engine.connect() as conn:
    #             # ATOMIC TRANSACTION: Auto-commits on success, Rolls back on error
    #             with conn.begin():
    #                 for statement in statements:
    #                     stmt = statement.strip()
    #                     if stmt:
    #                         conn.execute(text(stmt))
                            
    #         logger.info(f"Successfully executed SQL file: {file_path}")
    #     except Exception as e:
    #         logger.error(f"Database error executing {file_path}! Transaction rolled back: {e}")
    
    
    def _execute_sql_file(self, file_path: str) -> None:
        """Execute a SQL file as a single atomic transaction."""
        if not os.path.exists(file_path):
            file_path = os.path.join(os.getcwd(), file_path)
        if not os.path.exists(file_path):
            logger.error(f"Schema file not found at: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        statements = [s.strip() for s in sql_content.split(";") if s.strip()]

        try:
            with atomic_transaction(self.engine) as conn:
                for statement in statements:
                    conn.execute(text(statement))
            logger.info(f"Ingestion committed: {len(statements)} statements applied atomically.")
        except SQLAlchemyError as exc:
            logger.error(f"Ingestion rolled back — no partial data committed. Cause: {exc}")
            raise

    def bulk_ingest_validated(self, rows: list[dict], table: str, required_columns: set[str]) -> dict:
        """
        Validates every row against `required_columns` before any write occurs.
        Nothing is committed unless the entire batch passes validation.
        """
        missing = [i for i, row in enumerate(rows) if not required_columns.issubset(row.keys())]
        if missing:
            raise ValueError(f"Row validation failed at indices {missing}; ingestion aborted, nothing written.")

        columns = ", ".join(required_columns)
        placeholders = ", ".join(f":{c}" for c in required_columns)
        insert_stmt = text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})")

        try:
            with atomic_transaction(self.engine) as conn:
                for row in rows:
                    conn.execute(insert_stmt, {k: row[k] for k in required_columns})
            return {"status": "success", "rows_inserted": len(rows)}
        except SQLAlchemyError as exc:
            logger.error(f"Bulk ingest rolled back for table '{table}': {exc}")
            raise

    def execute(self, sql: str, params: dict = None) -> List[Dict[str, Any]]:
        """Execute a raw SQL query with optional params and return results as a list of dicts."""
        logger.info(f"Executing SQL: {sql}")
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                # Check if it's a SELECT query (returns rows)
                if result.returns_rows:
                    data = [dict(row) for row in result.mappings()]
                    logger.info(f"Execution complete. Returned {len(data)} rows.")
                    return data
                else:
                    conn.commit()
                    logger.info(f"Execution complete. Rows affected: {result.rowcount}")
                    return [{"status": "success", "rows_affected": result.rowcount}]
        except Exception as e:
            logger.error(f"DATABASE EXECUTION ERROR: {str(e)} | Query: {sql}")
            return []

    def execute_query(self, sql: str, params: dict = None) -> List[tuple] | List[Dict[str, Any]]:
        """Alias for execute() returning tuple rows when indexed or dicts when mapped."""
        logger.info(f"Executing Query: {sql}")
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                if result.returns_rows:
                    return result.fetchall()
                else:
                    conn.commit()
                    return []
        except Exception as e:
            logger.error(f"DATABASE EXECUTION ERROR: {str(e)} | Query: {sql}")
            return []

    def get_schema_info(self) -> List[str]:
        """Returns a list of 'table.column' strings for all tables in the database."""
        schema_info = []
        try:
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            for table in tables:
                columns = inspector.get_columns(table)
                for col in columns:
                    schema_info.append(f"{table}.{col['name']}")
            return schema_info
        except Exception as e:
            logger.error(f"Error fetching schema info: {e}")
            return []

db_service = DatabaseService()