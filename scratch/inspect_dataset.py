import sqlite3
import pandas as pd

df = pd.read_excel('live_data/shop_sales_test_dataset_100_rows.xlsx')
print("Columns:", df.columns.tolist())
print(df.head(2))
