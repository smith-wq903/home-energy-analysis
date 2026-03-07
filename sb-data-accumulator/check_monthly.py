import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

result = supabase.table("enevisata_monthly").select("year, month, usage_kwh").order("year").order("month").execute()

from collections import defaultdict
by_year = defaultdict(list)
for row in result.data:
    by_year[row["year"]].append(row)

print("=== enevisata_monthly ===")
for year in sorted(by_year.keys()):
    rows = by_year[year]
    print(f"  {year}年: {len(rows)}ヶ月分")
    for r in rows:
        print(f"    {r['month']:2d}月: {r['usage_kwh']} kWh")
