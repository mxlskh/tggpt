from supabase import create_client, Client
import os

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        self.client = create_client(url, key)

    def is_user_approved(self, user_id: int) -> bool:
        try:
            response = self.client.table("users").select("status").eq("id", str(user_id)).execute()
            users = response.data
            return bool(users and users[0].get("status") == "approved")
        except Exception as e:
            print(f"[ERROR] is_user_approved: {e}")
            return False

    def is_blocked(self, user_id: int) -> bool:
        try:
            response = self.client.table("blocked_users").select("*").eq("user_id", user_id).execute()
            return bool(response.data and len(response.data) > 0)
        except Exception as e:
            print(f"[ERROR] is_blocked: {e}")
            return False

    def get_pending_requests(self) -> list[dict]:
        try:
            response = self.client.table("join_requests").select("*").execute()
            return response.data or []
        except Exception as e:
            print(f"[ERROR] get_pending_requests: {e}")
            return []

    def get_requests(self) -> dict[str, dict]:
        """
        Возвращает все pending-заявки в формате {user_id: info_dict}.
        """
        try:
            pending = self.get_pending_requests()
            return {str(req.get("user_id")): req for req in pending}
        except Exception as e:
            print(f"[ERROR] get_requests: {e}")
            return {}

    def get_users(self) -> dict[str, dict]:
        """
        Возвращает всех одобренных пользователей из таблицы users в формате {id: record_dict}.
        """
        try:
            response = self.client.table("users").select("*").execute()
            records = response.data or []
            return {str(rec.get("id")): rec for rec in records}
        except Exception as e:
            print(f"[ERROR] get_users: {e}")
            return {}

    def get_blocked_users(self) -> list[int]:
        """
        Возвращает список user_id всех заблокированных пользователей.
        """
        try:
            response = self.client.table("blocked_users").select("user_id").execute()
            records = response.data or []
            return [item.get("user_id") for item in records]
        except Exception as e:
            print(f"[ERROR] get_blocked_users: {e}")
            return []

    def add_join_request(self, user_id: int, username: str):
        try:
            self.client.table("join_requests").insert({
                "user_id": user_id,
                "username": username
            }).execute()
        except Exception as e:
            print(f"[ERROR] add_join_request: {e}")

    def approve_user(self, user_id: int, username: str):
        try:
            self.client.table("users").insert({
                "id": str(user_id),
                "username": username,
                "status": "approved"
            }).execute()
            self.client.table("join_requests").delete().eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[ERROR] approve_user: {e}")

    def reject_user(self, user_id: int):
        try:
            self.client.table("join_requests").delete().eq("user_id", user_id).execute()
            self.client.table("blocked_users").insert({
                "user_id": user_id
            }).execute()
        except Exception as e:
            print(f"[ERROR] reject_user: {e}")
