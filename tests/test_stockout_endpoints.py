from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_stockout_risk_endpoint():
    response = client.get("/api/v1/stockout/risk?domain=retail_clothing&days=7&method=auto")
    assert response.status_code == 200
    data = response.json()
    assert "at_risk_products" in data
    assert "count" in data
    assert "domain" in data
    assert data["domain"] == "retail_clothing"
    assert isinstance(data["at_risk_products"], list)

def test_stockout_risk_endpoint_with_invalid_domain():
    response = client.get("/api/v1/stockout/risk?domain=invalid_domain")
    # Should still work but return empty or use default
    assert response.status_code == 200

def test_stockout_sku_detail_endpoint():
    response = client.get("/api/v1/stockout/sku/CL-001?domain=retail_clothing")
    # May return 404 if SKU doesn't exist, but should not 500
    assert response.status_code in [200, 404]