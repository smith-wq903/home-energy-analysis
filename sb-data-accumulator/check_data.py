import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
JST = timezone(timedelta(hours=9))
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

# enevisata_30min の直近3日分
since = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
result = supabase.table("enevisata_30min").select("recorded_at, usage_kwh").gte("recorded_at", since).order("recorded_at").execute()

from collections import defaultdict
by_date = defaultdict(list)
for row in result.data:
    dt = datetime.fromisoformat(row["recorded_at"]).astimezone(JST)
    by_date[dt.date()].append(row["usage_kwh"])

print("=== enevisata_30min 直近3日 ===")
for date, vals in sorted(by_date.items()):
    non_null = [v for v in vals if v is not None]
    print(f"  {date}: {len(vals)}コマ, うちデータあり={len(non_null)}コマ, 合計={sum(non_null):.1f}kWh")
