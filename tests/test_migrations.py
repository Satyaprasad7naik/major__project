import sqlite3
import tempfile
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.migrations import migration_001

def test_migration_creates_auto_insights_table():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        # Run migration
        migration_001.run_migration(conn)

        # Verify tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert 'auto_insights' in tables
        assert 'purchase_orders' in tables
        assert 'simulation_results' in tables

        # Verify auto_insights schema
        cursor = conn.execute("PRAGMA table_info(auto_insights)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert columns['insight_id'] == 'TEXT'
        assert columns['domain'] == 'TEXT'
        assert columns['insight_type'] == 'TEXT'
        assert columns['severity'] == 'TEXT'
        assert columns['status'] == 'TEXT'
        assert columns['created_at'] == 'TIMESTAMP'

        # Verify indexes
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='auto_insights'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert 'idx_auto_insights_domain_status' in indexes
        assert 'idx_auto_insights_created' in indexes
    finally:
        conn.close()
        os.unlink(db_path)

def test_migration_creates_purchase_orders_table():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        migration_001.run_migration(conn)

        cursor = conn.execute("PRAGMA table_info(purchase_orders)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert columns['po_id'] == 'TEXT'
        assert columns['sku'] == 'TEXT'
        assert columns['qty'] == 'INTEGER'
        assert columns['supplier_id'] == 'TEXT'
        assert columns['status'] == 'TEXT'
        assert columns['recommended_by'] == 'TEXT'
    finally:
        conn.close()
        os.unlink(db_path)

def test_migration_creates_simulation_results_table():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        conn = sqlite3.connect(db_path)
        migration_001.run_migration(conn)

        cursor = conn.execute("PRAGMA table_info(simulation_results)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert columns['run_id'] == 'TEXT'
        assert columns['scenario'] == 'TEXT'
        assert columns['domain'] == 'TEXT'
        assert columns['passed'] == 'BOOLEAN'
    finally:
        conn.close()
        os.unlink(db_path)

if __name__ == "__main__":
    test_migration_creates_auto_insights_table()
    test_migration_creates_purchase_orders_table()
    test_migration_creates_simulation_results_table()
    print("All migration tests passed!")