from supabase import create_client, Client
import os

class SupabaseClient:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        self.client = create_client(url, key)
        def table(self, table_name: str):
            return self.client.table(table_name)

    def is_user_approved(self, user_id: int) -> bool:
        try:
            blocked = self.is_blocked(user_id)
            if blocked:
                return False

            response = self.client.table("users").select("status").eq("id", str(user_id)).execute()
            users = response.data
            return bool(users and users[0].get("status") == "approved")
        except Exception as e:
            print(f"[ERROR] is_user_approved: {e}")
            return False

    def is_approved(self, user_id: int) -> bool:
        """
        Алиас для is_user_approved — чтобы is_allowed и другие проверки
        могли вызывать один и тот же метод.
        """
        return self.is_user_approved(user_id)

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

    def get_blocked_users(self) -> list[dict]:
        try:
            response = self.client.table("blocked_users").select("user_id, username").execute()
            return response.data or []
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
            # 1) Удалить из заблокированных, если там есть
            self.client.table("blocked_users")\
                .delete()\
                .eq("user_id", user_id)\
                .execute()

            # 2) Добавить в таблицу users
            self.client.table("users").insert({
                "id": str(user_id),
                "username": username,
                "status": "approved"
            }).execute()

            # 3) Удалить из join_requests
            self.client.table("join_requests")\
                .delete()\
                .eq("user_id", user_id)\
                .execute()
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

    def table(self, table_name: str):
        """
        Позволяет вызывать self.supabase.table('...') так же, как вы делали раньше.
        """
        return self.client.table(table_name)
    
    def block_user(self, user_id: int):
        try:
            # Получаем username перед удалением
            response = self.client.table("users").select("username").eq("id", str(user_id)).execute()
            username = response.data[0].get("username", "") if response.data else ""

            self.client.table("blocked_users").upsert({
                "user_id": user_id,
                "username": username
            }).execute()

            self.client.table("users").delete().eq("id", str(user_id)).execute()
        except Exception as e:
            print(f"[ERROR] block_user: {e}")

    def unblock_user(self, user_id: int):
        try:
            self.client.table("blocked_users").delete().eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[ERROR] unblock_user: {e}")

    def is_user_paid(self, user_id: int) -> bool:
        """
        Возвращает True, если пользователь оплатил подписку (paid == true).
        """
        try:
            resp = (
                self.client
                    .table("users")
                    .select("paid")
                    .eq("user_id", user_id)
                    .execute()
            )
            data = resp.data
            return bool(data and data[0].get("paid") is True)
        except Exception as e:
            print(f"[ERROR] is_user_paid: {e}")
            return False

    def mark_user_paid(self, user_id: int):
        """
        Помечает в базе пользователя как оплатившего подписку.
        """
        try:
            self.client.table("users").update({"paid": True}).eq("user_id", user_id).execute()
        except Exception as e:
            print(f"[ERROR] mark_user_paid: {e}")