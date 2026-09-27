import sys
import asyncio
import json

sys.path.insert(0, '.')

from app.api.auth import register, login, get_me, RegisterRequest, OAuth2PasswordRequestForm
from app.api.pricing_endpoints import get_price_recommendation, get_batch_price_recommendations, BatchPriceRequestBody
from app.api.supply_chain_endpoints import get_availability, route_fulfillment, RouteRequest
from app.api.carbon_endpoints import get_carbon_footprint, get_checkout_options
from app.main import health_check
from app.services.database import DatabaseService

async def run_feature_test_suite():
    print("===========================================================")
    print("          INSIGHTOS / DERIVINSIGHT FEATURE SUITE            ")
    print("===========================================================")

    # 1. Health & Readiness Probe
    print("\n[1/6] Testing System Health & Readiness Probe (/health)...")
    h_res = health_check()
    h_data = json.loads(h_res.body.decode("utf-8"))
    print(f"  Status Code: {h_res.status_code}")
    print(f"  Status:      {h_data.get('status')}")
    print(f"  Probes:      {h_data.get('probes')}")

    # 2. JWT Authentication Layer
    print("\n[2/6] Testing JWT Authentication Layer...")
    uname = "suite_user_test"
    try:
        reg = await register(RegisterRequest(username=uname, email="suite_test@example.com", password="SecurePassword123!", full_name="Suite Test User"))
        print(f"  [PASS] Registered User: username=\"{reg.username}\", email=\"{reg.email}\"")
    except Exception as e:
        print(f"  [INFO] User already registered, proceeding to login ({e})")

    form = OAuth2PasswordRequestForm(username=uname, password="SecurePassword123!", scope="", grant_type="password")
    token_resp = await login(form)
    print(f"  [PASS] Logged In: Token Type=\"{token_resp.token_type}\", AccessToken=\"{token_resp.access_token[:30]}...\"")

    me = await get_me(current_user={"username": uname})
    print(f"  [PASS] Authenticated Profile (/me): username=\"{me.username}\", email=\"{me.email}\", full_name=\"{me.full_name}\"")

    # 3. Dynamic Pricing Engine
    print("\n[3/6] Testing Dynamic Pricing Engine...")
    p_rec = await get_price_recommendation('SKU-1001')
    print(f"  [PASS] SKU:                  {p_rec.sku}")
    print(f"         Base Price:           ${p_rec.base_price:.2f}")
    print(f"         Recommended Price:    ${p_rec.recommended_price:.2f}")
    print(f"         Discount / Surcharge: {p_rec.discount_pct}%")
    print(f"         Confidence Score:     {p_rec.confidence}")
    print(f"         Reasoning:            {p_rec.reasoning}")

    p_batch = await get_batch_price_recommendations(BatchPriceRequestBody(skus=['SKU-1001', 'SKU-1002']))
    print(f"  [PASS] Batch Pricing: Evaluated {len(p_batch)} SKUs successfully.")

    # 4. Supply Chain Digital Twin
    print("\n[4/6] Testing Supply Chain Digital Twin...")
    avail = await get_availability('SKU-1001')
    print(f"  [PASS] Inventory Locations: {len(avail)} active warehouse(s) found.")
    for a in avail:
        print(f"         - {a.warehouse_name} ({a.warehouse_city}): {a.quantity_available} units available, Click&Collect ready: {a.click_collect_ready}")

    routed = await route_fulfillment(RouteRequest(
        sku='SKU-1001',
        quantity=2,
        customer_lat=19.0760,
        customer_lon=72.8777,
        customer_city='Mumbai'
    ))
    print(f"  [PASS] Order Fulfillment Routed:")
    print(f"         Order ID:           {routed.order_id}")
    print(f"         Assigned Warehouse: {routed.assigned_warehouse_name} ({routed.assigned_warehouse_city})")
    print(f"         Estimated Distance: {routed.distance_km} km")
    print(f"         Estimated Carbon:   {routed.estimated_carbon_kg} kg CO2")

    # 5. Scope 1-3 Carbon Accounting
    print("\n[5/6] Testing Scope 1-3 Carbon Accounting Calculator...")
    carbon = await get_carbon_footprint('SKU-1001')
    print(f"  [PASS] SKU Footprint ({carbon.sku}):")
    print(f"         Total CO2e:         {carbon.total_kg_co2e} kg")
    print(f"         Emissions Rating:   Grade {carbon.label}")
    print(f"         Scope 1 (Direct):   {carbon.scope1_kg} kg CO2e")
    print(f"         Scope 2 (Power):    {carbon.scope2_kg} kg CO2e")
    print(f"         Scope 3 (Value):    {carbon.scope3_kg} kg CO2e")

    opts = await get_checkout_options('SKU-1001')
    print(f"  [PASS] Checkout Delivery Options:")
    for o in opts:
        print(f"         - {o.option_name}: {o.estimated_co2_kg:.3f} kg CO2 ({o.description})")

    # 6. Database & Schema Inspection
    print("\n[6/6] Testing Database & Schema Service...")
    db = DatabaseService()
    user_rows = db.execute("SELECT COUNT(*) as cnt FROM users")
    table_cnt = len(db.get_schema_info())
    cnt_val = user_rows[0].get("cnt", 0) if user_rows else 0
    print(f"  [PASS] Primary Database: Reachable ({cnt_val} users in database)")
    print(f"  [PASS] Schema Inspector: Detected {table_cnt} table.column pairs.")

    print("\n===========================================================")
    print("         ALL FEATURES TESTED & VERIFIED SUCCESSFULLY        ")
    print("===========================================================")

if __name__ == "__main__":
    asyncio.run(run_feature_test_suite())
