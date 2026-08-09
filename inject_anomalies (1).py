"""
inject_anomalies.py

Layers the five required threat-vector scenarios onto an EXISTING,
already-populated derivinsightnew.db -- it does not regenerate users,
transactions, or login_events. It reads real users already in your
database and injects new, clearly-tagged rows on top of them.

Safe to run once against your current 500-user / 50,000-txn /
20,000-login dataset. Re-running it will inject a second, independent
set of anomalies (it does not check for prior runs) -- back up your
.db file first if you want to experiment.

Run:
    python inject_anomalies.py
"""

import sqlite3
import uuid
import random
from datetime import datetime, timedelta

from faker import Faker

DB_PATH = "derivinsightnew.db"
RANDOM_SEED = 7

USD_RATES = {"USD": 1.0, "EUR": 1.08, "BTC": 62000.0, "ETH": 3400.0, "SOL": 145.0}

fake = Faker()
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


def new_ipv4():
    return fake.ipv4()


def device_bundle():
    device_type = random.choice(["MOBILE", "DESKTOP", "TABLET"])
    ua = fake.user_agent()
    fingerprint = uuid.uuid4().hex[:32]
    return device_type, ua, fingerprint


def insert_login(cur, user, ip, country, status, failure_reason, created_at):
    cur.execute(
        """INSERT INTO login_events (event_id, user_id, email_attempted, ip_address,
           country, city, device_type, device_fingerprint, user_agent, status,
           failure_reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            f"EVT-{uuid.uuid4().hex[:10].upper()}",
            user["user_id"], user["email"], ip, country, fake.city(),
            *device_bundle()[:2], device_bundle()[2],
            status, failure_reason, created_at.isoformat(),
        ),
    )


def insert_txn(cur, user, txn_type, amount, currency, status, flag_reason,
                payment_method, ip, created_at, instrument=None):
    amount_usd = round(amount * USD_RATES.get(currency, 1.0), 2)
    cur.execute(
        """INSERT INTO transactions (txn_id, user_id, txn_type, instrument, amount,
           currency, amount_usd, status, flag_reason, payment_method, external_ref,
           ip_address, created_at, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            f"TXN-{uuid.uuid4().hex[:10].upper()}", user["user_id"], txn_type,
            instrument, amount, currency, amount_usd, status, flag_reason,
            payment_method, uuid.uuid4().hex[:16], ip, created_at.isoformat(),
            (created_at + timedelta(seconds=60)).isoformat() if status == "COMPLETED" else None,
        ),
    )


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    active_users = [dict(r) for r in cur.execute(
        "SELECT user_id, email, country, created_at FROM users WHERE account_status = 'ACTIVE'"
    ).fetchall()]
    all_users = [dict(r) for r in cur.execute(
        "SELECT user_id, email, country, created_at FROM users"
    ).fetchall()]

    if len(active_users) < 6:
        raise SystemExit(
            f"Need at least 6 active users to inject all scenarios distinctly; found {len(active_users)}."
        )

    injected_summary = {}

    # -------------------------------------------------------------
    # (a) ACCOUNT TAKEOVER (ATO) + CRYPTO CASHOUT -- 2 active accounts
    # -------------------------------------------------------------
    ato_victims = random.sample(active_users, 2)
    for victim in ato_victims:
        foreign_ip = new_ipv4()
        attack_start = datetime.now() - timedelta(days=random.uniform(1, 60))

        for i in range(5):
            insert_login(cur, victim, foreign_ip, random.choice(["RU", "NG", "CN", "BR"]),
                         "FAILED", "WRONG_PASSWORD", attack_start + timedelta(minutes=i))

        success_time = attack_start + timedelta(minutes=5)
        insert_login(cur, victim, foreign_ip, random.choice(["RU", "NG", "CN", "BR"]),
                     "SUCCESS", None, success_time)

        cashout_time = success_time + timedelta(minutes=random.randint(1, 3))
        btc_amount = round(random.uniform(0.8, 5.0), 4)
        insert_txn(cur, victim, "WITHDRAWAL", btc_amount, "BTC", "COMPLETED",
                   "SUSPECTED_ATO_CASHOUT", "CRYPTO", foreign_ip, cashout_time, "BTC/USD")

    injected_summary["a_ato_cashout"] = [u["user_id"] for u in ato_victims]

    # -------------------------------------------------------------
    # (b) CREDENTIAL STUFFING -- 30 attempts / 15 users / 1 IP / 10 min
    # -------------------------------------------------------------
    stuffing_ip = new_ipv4()
    stuffing_start = datetime.now() - timedelta(days=random.uniform(1, 45))
    stuffing_targets = random.sample(all_users, 15)
    for i in range(30):
        target = stuffing_targets[i % 15]
        insert_login(cur, target, stuffing_ip, random.choice(["RU", "VN", "UA"]),
                     "FAILED", "WRONG_PASSWORD",
                     stuffing_start + timedelta(seconds=random.randint(0, 599)))

    injected_summary["b_credential_stuffing_ip"] = stuffing_ip

    # -------------------------------------------------------------
    # (c) DORMANT ACCOUNT LIQUIDATION -- 18+ months old, sudden activity
    # -------------------------------------------------------------
    dormant_candidates = [
        u for u in all_users
        if datetime.fromisoformat(u["created_at"]) < datetime.now() - timedelta(days=548)
    ]
    dormant_user = random.choice(dormant_candidates) if dormant_candidates else random.choice(all_users)

    login_now = datetime.now() - timedelta(minutes=random.randint(5, 30))
    fresh_ip = new_ipv4()
    insert_login(cur, dormant_user, fresh_ip, dormant_user["country"], "SUCCESS", None, login_now)

    sell_time = login_now + timedelta(minutes=2)
    insert_txn(cur, dormant_user, "SELL", 1000000.0, "USD", "COMPLETED",
               "DORMANT_ACCOUNT_LIQUIDATION", "CRYPTO", fresh_ip, sell_time, "BTC/USD")

    withdrawal_time = sell_time + timedelta(minutes=3)
    insert_txn(cur, dormant_user, "WITHDRAWAL", 1000000.0, "USD", "COMPLETED",
               "DORMANT_ACCOUNT_LIQUIDATION", "BANK_TRANSFER", fresh_ip, withdrawal_time)

    injected_summary["c_dormant_liquidation"] = dormant_user["user_id"]

    # -------------------------------------------------------------
    # (d) HIGH-VALUE VIP CHURN/SUSPENSION -- 3 whale users
    # -------------------------------------------------------------
    whale_candidates = random.sample([u for u in active_users if u not in ato_victims], 3)
    for whale in whale_candidates:
        churn_start = datetime.now() - timedelta(days=random.uniform(1, 30))
        for i in range(4):
            amt = round(random.uniform(80000, 500000), 2)
            insert_txn(cur, whale, "DEPOSIT", amt, "USD", "FAILED",
                       "VIP_DEPOSIT_FAILURE_PRECEDING_SUSPENSION", "BANK_TRANSFER",
                       new_ipv4(), churn_start + timedelta(days=i))
        cur.execute(
            "UPDATE users SET account_status = 'SUSPENDED', updated_at = ? WHERE user_id = ?",
            ((churn_start + timedelta(days=4)).isoformat(), whale["user_id"]),
        )

    injected_summary["d_vip_churn"] = [u["user_id"] for u in whale_candidates]

    # -------------------------------------------------------------
    # (e) IMPOSSIBLE TRAVEL -- 1 user, US then foreign, 10 min apart
    # -------------------------------------------------------------
    remaining = [u for u in active_users if u not in ato_victims and u not in whale_candidates]
    travel_user = random.choice(remaining) if remaining else random.choice(active_users)

    us_time = datetime.now() - timedelta(days=random.uniform(1, 20))
    insert_login(cur, travel_user, new_ipv4(), "US", "SUCCESS", None, us_time)

    foreign_time = us_time + timedelta(minutes=10)
    insert_login(cur, travel_user, new_ipv4(), random.choice(["JP", "SG", "DE", "FR"]),
                 "SUCCESS", None, foreign_time)

    injected_summary["e_impossible_travel"] = travel_user["user_id"]

    conn.commit()
    conn.close()

    print("Anomalies injected into", DB_PATH)
    for k, v in injected_summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
