-- Retail Clothing Domain Schema
-- Auto-generated from retail_clothing.db
-- Tables: suppliers, products, inventory, sales_events

CREATE TABLE inventory (
    sku              TEXT PRIMARY KEY REFERENCES products(sku),
    location         TEXT NOT NULL,
    stock_count      INTEGER NOT NULL DEFAULT 0,
    reorder_point    INTEGER NOT NULL DEFAULT 5,
    last_restocked_at TEXT
);

CREATE TABLE products (
    sku              TEXT PRIMARY KEY,
    style_name       TEXT NOT NULL,
    category         TEXT NOT NULL,
    size             TEXT NOT NULL,
    color            TEXT NOT NULL,
    unit_cost        REAL NOT NULL,
    retail_price     REAL NOT NULL,
    supplier_id      TEXT NOT NULL REFERENCES suppliers(supplier_id),
    created_at       TEXT NOT NULL
);

CREATE TABLE sales_events (
    event_id         TEXT PRIMARY KEY,
    sku              TEXT NOT NULL REFERENCES products(sku),
    units_sold       INTEGER NOT NULL,
    sale_date        TEXT NOT NULL,
    channel          TEXT NOT NULL
);

CREATE TABLE suppliers (
    supplier_id      TEXT PRIMARY KEY,
    supplier_name    TEXT NOT NULL,
    lead_time_days   INTEGER NOT NULL,
    on_time_rate     REAL NOT NULL,
    country          TEXT NOT NULL
);
