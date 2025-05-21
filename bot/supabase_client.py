import os
from supabase import create_client, Client
import asyncio

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        self.client: Client = create_client(url, key)

    async def is_user_approved(self, user_id: int) -> bool:
        try:
            response = await self.client.from_("users").select("status").eq("id", str(user_id)).execute()
            users = response.data
            return bool(users and users[0].get("status") == "approved")
        except Exception as e:
            print(f"[ERROR] is_user_approved: {e}")
            return False

    async def is_blocked(self, user_id: int) -> bool:
        try:
            response = await self.client.from_("blocked_users").select("*").eq("user_id", user_id).execute()
            return bool(response.data)
        except Exception as e:
            print(f"[ERROR] is_blocked: {e}")
            return False

    async def get_pending_requests(self):
        try:
            response = await self.client.from_("join_requests").select("*").execute()
            return response.data or []
        except Exception as e:
            print(f"[ERROR] get_pending_requests: {e}")
            return []

    async def add_join_request(self, user_id: int, username: str):
        try:
            await self.client.from_("join_requests").insert({
                "user_id": user_id,
                "username": username
            }).execute()
        except Exception as e:
            print(f"[ERROR] add_join_request: {e}")

    async def approve_user(self, user_id: int, username: str):
        try:
            await self.client.from_("users").upsert({
                "id": str(user_id),
                "username": username,
                "status": "approved"
            }).execute()
            await self.client.from_("join_requests").delete().eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[ERROR] approve_user: {e}")

    async def reject_user(self, user_id: int):
        try:
            await self.client.from_("join_requests").delete().eq("user_id", user_id).execute()
            await self.client.from_("blocked_users").insert({
                "user_id": user_id
            }).execute()
        except Exception as e:
            print(f"[ERROR] reject_user: {e}")
