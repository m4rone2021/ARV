"""Quick sanity check that the Supabase data layer works."""

import sys
sys.path.insert(0, r"C:\Users\admin\ARV")

from database import sb

def main():
    print("Connecting to Supabase...")
    client = sb()
    print("  OK\n")

    tables = [
        "master_items",
        "users",
        "transactions",
        "deliveries",
        "discrepancies",
        "reminders",
        "user_logs",
        "physical_inventory_logs",
    ]

    print(f"{'Table':<28} {'Rows':>6}")
    print("-" * 36)
    total = 0
    for t in tables:
        try:
            res = client.table(t).select("id", count="exact").execute()
            print(f"{t:<28} {res.count:>6}")
            total += res.count
        except Exception as e:
            print(f"{t:<28} ERROR: {e}")
    print("-" * 36)
    print(f"{'TOTAL':<28} {total:>6}")

    # Spot check: first 3 master_items
    print("\nSample master_items:")
    items = client.table("master_items").select("item_name, category, current_stock").limit(3).execute()
    for it in items.data:
        print(f"  - {it['item_name']}  ({it['category']})  stock={it['current_stock']}")


if __name__ == "__main__":
    main()
