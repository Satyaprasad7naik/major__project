"""
Utility script to generate sample Excel files in live_data/ directory for InsightOS live sync testing.
"""

import os
import pandas as pd


def create_sample_excel_files(live_data_dir: str = "live_data"):
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(project_dir, live_data_dir)
    os.makedirs(target_dir, exist_ok=True)

    # 1. Products Excel (compatible with both sku/style_name and product_id/name)
    products_df = pd.DataFrame([
        {
            "sku": "SKU-3001",
            "style_name": "Classic Wool Coat",
            "category": "Outerwear",
            "size": "L",
            "color": "Navy",
            "unit_cost": 45.00,
            "retail_price": 120.00,
            "supplier_id": "SUP-001",
            "created_at": "2026-09-01"
        },
        {
            "sku": "SKU-3002",
            "style_name": "Slim Fit Chinos",
            "category": "Apparel",
            "size": "M",
            "color": "Beige",
            "unit_cost": 18.00,
            "retail_price": 49.99,
            "supplier_id": "SUP-002",
            "created_at": "2026-09-01"
        },
        {
            "sku": "SKU-3003",
            "style_name": "Merino Sweater",
            "category": "Knitwear",
            "size": "M",
            "color": "Grey",
            "unit_cost": 25.00,
            "retail_price": 65.00,
            "supplier_id": "SUP-001",
            "created_at": "2026-09-01"
        },
        {
            "sku": "SKU-3004",
            "style_name": "Leather Boots",
            "category": "Footwear",
            "size": "42",
            "color": "Brown",
            "unit_cost": 50.00,
            "retail_price": 135.00,
            "supplier_id": "SUP-003",
            "created_at": "2026-09-01"
        }
    ])
    products_path = os.path.join(target_dir, "products.xlsx")
    products_df.to_excel(products_path, index=False, sheet_name="Products")
    print(f"Created sample products file: {products_path}")

    # 2. Inventory Excel (includes location & stock_count/current_stock)
    inventory_df = pd.DataFrame([
        {"sku": "SKU-3001", "location": "Warehouse-Delhi", "stock_count": 2, "reorder_point": 10, "last_restocked_at": "2026-08-20"},
        {"sku": "SKU-3002", "location": "Warehouse-Mumbai", "stock_count": 45, "reorder_point": 15, "last_restocked_at": "2026-08-25"},
        {"sku": "SKU-3003", "location": "Warehouse-Bengaluru", "stock_count": 1, "reorder_point": 8, "last_restocked_at": "2026-08-18"},
        {"sku": "SKU-3004", "location": "Store-Chennai", "stock_count": 0, "reorder_point": 5, "last_restocked_at": "2026-08-15"}
    ])
    inventory_path = os.path.join(target_dir, "inventory.xlsx")
    inventory_df.to_excel(inventory_path, index=False, sheet_name="Inventory")
    print(f"Created sample inventory file: {inventory_path}")

    # 3. Sales Excel (includes units_sold & channel)
    sales_df = pd.DataFrame([
        {"event_id": "SE-3001-01", "sku": "SKU-3001", "units_sold": 8, "sale_date": "2026-09-01", "channel": "Online"},
        {"event_id": "SE-3002-01", "sku": "SKU-3002", "units_sold": 15, "sale_date": "2026-09-01", "channel": "In-Store"},
        {"event_id": "SE-3003-01", "sku": "SKU-3003", "units_sold": 6, "sale_date": "2026-09-01", "channel": "Online"},
        {"event_id": "SE-3004-01", "sku": "SKU-3004", "units_sold": 10, "sale_date": "2026-09-01", "channel": "In-Store"}
    ])
    sales_path = os.path.join(target_dir, "sales.xlsx")
    sales_df.to_excel(sales_path, index=False, sheet_name="Sales")
    print(f"Created sample sales file: {sales_path}")


if __name__ == "__main__":
    create_sample_excel_files()
