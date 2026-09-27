"""
Intent Classification Model — Training Script
===============================================
Trains a TF-IDF + Logistic Regression model on curated retail domain questions.
Produces: intent_model.pkl, tfidf_vectorizer.pkl

Algorithm: TF-IDF Vectorizer → Logistic Regression (simple, explainable, fast)
Classes: stockout_risk, reorder_recommendation, sales_analysis,
         inventory_status, general_query, schema_query, off_topic
"""

import os
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# ── Training Data: Curated question → intent pairs ──────────────────────────

TRAINING_DATA = [
    # ── stockout_risk ────────────────────────────────────────────────────────
    ("Which products will run out of stock this week?", "stockout_risk"),
    ("What items are at risk of stockout?", "stockout_risk"),
    ("Show me products that might go out of stock", "stockout_risk"),
    ("Which SKUs have critically low inventory?", "stockout_risk"),
    ("What products are running low on stock?", "stockout_risk"),
    ("Are any products about to run out?", "stockout_risk"),
    ("Show stockout risk analysis", "stockout_risk"),
    ("Products below reorder point", "stockout_risk"),
    ("Which items need urgent restocking?", "stockout_risk"),
    ("Low stock alert products", "stockout_risk"),
    ("Critical inventory levels", "stockout_risk"),
    ("What is at risk of going out of stock?", "stockout_risk"),
    ("Show me items below their reorder threshold", "stockout_risk"),
    ("Products with less than 5 units left", "stockout_risk"),
    ("Which styles are almost sold out?", "stockout_risk"),
    ("Stockout probability for this week", "stockout_risk"),
    ("Items with zero stock", "stockout_risk"),
    ("Out of stock products", "stockout_risk"),
    ("Which products have stock count below reorder point?", "stockout_risk"),
    ("Show products that will run out in 3 days", "stockout_risk"),
    ("Days of cover for all products", "stockout_risk"),
    ("Products with highest stockout probability", "stockout_risk"),
    ("What items are critically low?", "stockout_risk"),
    ("Show me stockout risks across all categories", "stockout_risk"),
    ("Risk assessment for inventory", "stockout_risk"),
    ("Which products have dangerously low stock?", "stockout_risk"),
    ("Inventory risk report", "stockout_risk"),
    ("Products running out soon", "stockout_risk"),
    ("Alert me about low stock items", "stockout_risk"),
    ("Which SKUs are at critical level?", "stockout_risk"),

    # ── reorder_recommendation ────────────────────────────────────────────────
    ("How much should I reorder for product X?", "reorder_recommendation"),
    ("Suggest reorder quantities", "reorder_recommendation"),
    ("What should I reorder this week?", "reorder_recommendation"),
    ("Generate purchase order recommendations", "reorder_recommendation"),
    ("Reorder suggestions for low stock items", "reorder_recommendation"),
    ("How many units should I order?", "reorder_recommendation"),
    ("Create a purchase order for restocking", "reorder_recommendation"),
    ("What quantities do I need to reorder?", "reorder_recommendation"),
    ("Recommend restock quantities", "reorder_recommendation"),
    ("Draft a PO for items below reorder point", "reorder_recommendation"),
    ("Suggest restocking plan", "reorder_recommendation"),
    ("Auto-generate purchase orders", "reorder_recommendation"),
    ("What should I buy to prevent stockouts?", "reorder_recommendation"),
    ("Reorder plan for next week", "reorder_recommendation"),
    ("Purchase order draft for critical items", "reorder_recommendation"),
    ("How many Headphones should I order?", "reorder_recommendation"),
    ("Optimal reorder quantity for SKU-1001", "reorder_recommendation"),
    ("Calculate reorder point for all products", "reorder_recommendation"),
    ("What is the recommended order quantity?", "reorder_recommendation"),
    ("Restocking recommendation report", "reorder_recommendation"),
    ("Suggest how many units to reorder", "reorder_recommendation"),
    ("Generate restocking plan", "reorder_recommendation"),
    ("Purchase suggestion for low items", "reorder_recommendation"),
    ("How much inventory should I order?", "reorder_recommendation"),
    ("Replenishment recommendations", "reorder_recommendation"),
    ("Should I place an order for Tumbler or Keyboard?", "reorder_recommendation"),
    ("Reorder amounts for all products", "reorder_recommendation"),
    ("Auto purchase order for Electronics and Home goods", "reorder_recommendation"),
    ("Recommended order quantities for all retail categories", "reorder_recommendation"),
    ("Buying guide for this month", "reorder_recommendation"),

    # ── sales_analysis ────────────────────────────────────────────────────────
    ("Show me top selling products", "sales_analysis"),
    ("What are the best selling items?", "sales_analysis"),
    ("Sales report for last month", "sales_analysis"),
    ("Revenue by product category", "sales_analysis"),
    ("Which products generated the most revenue?", "sales_analysis"),
    ("Sales trends this quarter", "sales_analysis"),
    ("Total revenue from Denim Jeans", "sales_analysis"),
    ("How many units were sold last week?", "sales_analysis"),
    ("Show sales data for all products", "sales_analysis"),
    ("Top 10 products by units sold", "sales_analysis"),
    ("Sales analysis by channel", "sales_analysis"),
    ("Daily sales report", "sales_analysis"),
    ("Monthly sales performance", "sales_analysis"),
    ("Which category has highest sales?", "sales_analysis"),
    ("Product performance analysis", "sales_analysis"),
    ("Revenue breakdown by size and color", "sales_analysis"),
    ("Sales velocity for trending items", "sales_analysis"),
    ("Compare online vs store sales", "sales_analysis"),
    ("Average order value this month", "sales_analysis"),
    ("Show me sales growth trends", "sales_analysis"),
    ("Which style sold the most?", "sales_analysis"),
    ("Weekly sales summary", "sales_analysis"),
    ("Total units sold today", "sales_analysis"),
    ("Revenue per product", "sales_analysis"),
    ("Sales performance dashboard", "sales_analysis"),
    ("Slow moving products", "sales_analysis"),
    ("Top performers this week", "sales_analysis"),
    ("Sales by supplier", "sales_analysis"),
    ("How is product X selling?", "sales_analysis"),
    ("Year over year sales comparison", "sales_analysis"),

    # ── inventory_status ──────────────────────────────────────────────────────
    ("Show me current inventory levels", "inventory_status"),
    ("What is the stock count for SKU-1001?", "inventory_status"),
    ("List all products with their stock levels", "inventory_status"),
    ("How much stock do we have?", "inventory_status"),
    ("Inventory snapshot", "inventory_status"),
    ("Current stock for Leather Boots", "inventory_status"),
    ("Show all products in warehouse", "inventory_status"),
    ("Check stock for size Medium", "inventory_status"),
    ("Inventory count by location", "inventory_status"),
    ("How many items are in stock?", "inventory_status"),
    ("Product catalog with stock levels", "inventory_status"),
    ("Inventory summary report", "inventory_status"),
    ("Total inventory value", "inventory_status"),
    ("Stock levels by category", "inventory_status"),
    ("Show me inventory by color", "inventory_status"),
    ("Which products are fully stocked?", "inventory_status"),
    ("Warehouse inventory report", "inventory_status"),
    ("Products available in store", "inventory_status"),
    ("Stock status for all SKUs", "inventory_status"),
    ("Current inventory breakdown", "inventory_status"),
    ("What do we have in inventory?", "inventory_status"),
    ("Full stock report", "inventory_status"),
    ("Inventory levels across all locations", "inventory_status"),
    ("How much of each product do we have?", "inventory_status"),
    ("Products with more than 100 units", "inventory_status"),
    ("List all products", "inventory_status"),
    ("Show me the product catalog", "inventory_status"),
    ("What products do we carry?", "inventory_status"),
    ("All items in stock", "inventory_status"),
    ("Check inventory for supplier ABC", "inventory_status"),

    # ── general_query ─────────────────────────────────────────────────────────
    ("Show me supplier information", "general_query"),
    ("What suppliers do we work with?", "general_query"),
    ("List all suppliers and their lead times", "general_query"),
    ("Supplier performance report", "general_query"),
    ("Which supplier has the fastest delivery?", "general_query"),
    ("Show supplier on-time delivery rates", "general_query"),
    ("Contact details for suppliers", "general_query"),
    ("Lead time analysis for suppliers", "general_query"),
    ("Show purchase order history", "general_query"),
    ("List all pending purchase orders", "general_query"),
    ("What purchase orders are open?", "general_query"),
    ("PO status report", "general_query"),
    ("Show me the data in the system", "general_query"),
    ("Give me a summary of the business", "general_query"),
    ("Overview of the system data", "general_query"),
    ("Show me everything", "general_query"),
    ("General business report", "general_query"),
    ("What data do you have?", "general_query"),
    ("System status", "general_query"),
    ("Dashboard overview", "general_query"),
    ("Recent activity report", "general_query"),
    ("Show me insights", "general_query"),
    ("Give me a quick summary", "general_query"),
    ("What can you tell me?", "general_query"),
    ("Business intelligence report", "general_query"),
    ("Show sync logs", "general_query"),
    ("Recent data imports", "general_query"),
    ("Data quality report", "general_query"),
    ("Performance metrics", "general_query"),
    ("Show me the latest updates", "general_query"),

    # ── schema_query ──────────────────────────────────────────────────────────
    ("What tables are available?", "schema_query"),
    ("Show me the database schema", "schema_query"),
    ("List all columns in the products table", "schema_query"),
    ("What fields does the inventory table have?", "schema_query"),
    ("Database structure", "schema_query"),
    ("What tables can I query?", "schema_query"),
    ("Show schema", "schema_query"),
    ("What columns exist?", "schema_query"),
    ("Describe the database", "schema_query"),
    ("What data model do you use?", "schema_query"),
    ("Show me table definitions", "schema_query"),
    ("What are the database tables?", "schema_query"),
    ("List all tables and columns", "schema_query"),
    ("Schema information", "schema_query"),
    ("What can I ask about?", "schema_query"),
    ("What kind of queries can I run?", "schema_query"),
    ("Help me understand the data", "schema_query"),
    ("What entities are in the system?", "schema_query"),
    ("Explain the data model", "schema_query"),
    ("What capabilities do you have?", "schema_query"),

    # ── off_topic ─────────────────────────────────────────────────────────────
    ("What is the weather today?", "off_topic"),
    ("Tell me a joke", "off_topic"),
    ("Who won the cricket match?", "off_topic"),
    ("Hello how are you?", "off_topic"),
    ("Hi", "off_topic"),
    ("Good morning", "off_topic"),
    ("What is AI?", "off_topic"),
    ("Explain machine learning", "off_topic"),
    ("Who is the president?", "off_topic"),
    ("Tell me about Python programming", "off_topic"),
    ("What time is it?", "off_topic"),
    ("How to cook pasta?", "off_topic"),
    ("Play a song", "off_topic"),
    ("What is the meaning of life?", "off_topic"),
    ("Thank you", "off_topic"),
    ("Goodbye", "off_topic"),
    ("Hey there", "off_topic"),
    ("Good afternoon", "off_topic"),
    ("Nice to meet you", "off_topic"),
    ("Can you help me with homework?", "off_topic"),
]


def train_intent_model(save_dir: str = None):
    """
    Train and save the Intent Classification model.

    Returns:
        dict with accuracy, classification_report, and model paths
    """
    if save_dir is None:
        save_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(save_dir, exist_ok=True)

    # Prepare data
    texts = [item[0] for item in TRAINING_DATA]
    labels = [item[1] for item in TRAINING_DATA]

    print(f"[Intent Classifier] Training data: {len(texts)} samples")
    print(f"[Intent Classifier] Classes: {sorted(set(labels))}")
    print(f"[Intent Classifier] Distribution: {dict(zip(*np.unique(labels, return_counts=True)))}")

    # Split into train/test (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    # TF-IDF Vectorizer
    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),  # Unigrams + bigrams for better context
        stop_words="english",
        lowercase=True,
        sublinear_tf=True,  # Apply log normalization
    )

    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_test_tfidf = vectorizer.transform(X_test)

    # Logistic Regression with class balancing
    model = LogisticRegression(
        max_iter=1000,
        C=1.0,
        class_weight="balanced",
        solver="lbfgs",
        random_state=42,
    )

    model.fit(X_train_tfidf, y_train)

    # Evaluate
    y_pred = model.predict(X_test_tfidf)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)

    print(f"\n[Intent Classifier] Test Accuracy: {accuracy:.4f}")
    print(f"[Intent Classifier] Classification Report:\n{report}")

    # Save model and vectorizer
    model_path = os.path.join(save_dir, "intent_model.pkl")
    vectorizer_path = os.path.join(save_dir, "tfidf_vectorizer.pkl")

    joblib.dump(model, model_path)
    joblib.dump(vectorizer, vectorizer_path)

    print(f"[Intent Classifier] Model saved to: {model_path}")
    print(f"[Intent Classifier] Vectorizer saved to: {vectorizer_path}")

    return {
        "accuracy": accuracy,
        "report": report,
        "model_path": model_path,
        "vectorizer_path": vectorizer_path,
        "num_samples": len(texts),
        "num_classes": len(set(labels)),
    }


if __name__ == "__main__":
    result = train_intent_model()
    print(f"\n[SUCCESS] Training complete. Accuracy: {result['accuracy']:.2%}")
