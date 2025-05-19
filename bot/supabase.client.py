from supabase import create_client, Client
import os

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")  # Используй один и тот же ключ
        self.client: Client = create_client(url, key)

    def is_user_approved(self, user_id: int) -> bool:
        response = self.client.table("users").select("approved").eq("user_id", user_id).execute()
        if response.error:
            return False
        users = response.data
        return bool(users and users[0].get("approved", False))

    def get_approved_users(self):
        response = self.client.table("users").select("*").eq("status", "approved").execute()
        return response.data

    def get_pending_requests(self):
        response = self.client.table("join_requests").select("*").execute()
        return response.data

    def add_join_request(self, user_id: int, username: str):
        self.client.table("join_requests").insert({
            "user_id": user_id,
            "username": username
        }).execute()

    def approve_user(self, user_id: int, username: str):
        # Добавляем в users
        self.client.table("users").insert({
            "user_id": user_id,
            "username": username,
            "status": "approved"
        }).execute()

        # Удаляем из join_requests
        self.client.table("join_requests").delete().eq("user_id", user_id).execute()

    def reject_user(self, user_id: int):
        # Удаляем из join_requests
        self.client.table("join_requests").delete().eq("user_id", user_id).execute()
        
        # Добавляем в blocked_users
        self.client.table("blocked_users").insert({"user_id": user_id}).execute()

    def is_blocked(self, user_id: int) -> bool:
        response = self.client.table("blocked_users").select("*").eq("user_id", user_id).execute()
        return len(response.data) > 0