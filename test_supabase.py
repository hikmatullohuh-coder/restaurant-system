import os

from dotenv import load_dotenv
from supabase import create_client


load_dotenv()


supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SECRET_KEY")


if not supabase_url:
    raise RuntimeError("SUPABASE_URL не найден в .env")


if not supabase_key:
    raise RuntimeError("SUPABASE_SECRET_KEY не найден в .env")


supabase = create_client(
    supabase_url,
    supabase_key
)


result = (
    supabase
    .table("menu_items")
    .select("id, name, price")
    .limit(10)
    .execute()
)


print("SUPABASE CONNECTION: OK")
print()

for item in result.data:
    print(
        f'{item["id"]}. '
        f'{item["name"]} — '
        f'{item["price"]} сум'
    )