from supabase import create_client, Client
import os

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        self.client: Client = create_client(url, key)

    def is_user_approved(self, user_id: int) -> bool:
        response = self.client.table("users").select("status").eq("id", str(user_id)).execute()
        if response.error:
            return False
        users = response.data
        return bool(users and users[0].get("status") == "approved")


    def get_approved_users(self):
        response = self.client.table("users").select("*").eq("status", "approved").execute()
        if response.status_code != 200:
            return []
        return response.data

    def get_pending_requests(self):
        response = self.client.table("join_requests").select("*").execute()
        if response.status_code != 200:
            return []
        return response.data

    def add_join_request(self, user_id: int, username: str):
        response = self.client.table("join_requests").insert({
            "user_id": user_id,
            "username": username
        }).execute()
        if response.status_code != 201:  # 201 Created
            # Здесь можно добавить логирование ошибки или raise
            pass

    def approve_user(self, user_id: int, username: str):
        # Добавляем пользователя в users
        response_insert = self.client.table("users").insert({
            "id": str(user_id),  # Обрати внимание — в users поле id, а не user_id
            "username": username,
            "status": "approved"
        }).execute()
        if response_insert.status_code != 201:
            # обработать ошибку
            pass

        # Удаляем из join_requests
        response_delete = self.client.table("join_requests").delete().eq("user_id", user_id).execute()
        if response_delete.status_code != 200:
            # обработать ошибку
            pass

    def reject_user(self, user_id: int):
        # Удаляем из join_requests
        response_delete = self.client.table("join_requests").delete().eq("user_id", user_id).execute()
        if response_delete.status_code != 200:
            # обработать ошибку
            pass
        
        # Добавляем в blocked_users
        response_insert = self.client.table("blocked_users").insert({"user_id": user_id}).execute()
        if response_insert.status_code != 201:
            # обработать ошибку
            pass

    def is_blocked(self, user_id: int) -> bool:
        response = self.client.table("blocked_users").select("*").eq("user_id", user_id).execute()
        if response.status_code != 200:
            return False
        return bool(response.data and len(response.data) > 0)
