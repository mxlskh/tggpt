import os
import json
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class Database:
    def __init__(self, data_dir="data", admin_user_ids=None):
        self.DATA_DIR = data_dir
        if not os.path.exists(self.DATA_DIR):
            os.makedirs(self.DATA_DIR)
        self.admin_user_ids = admin_user_ids or []

    def load_json(self, filename):
        path = os.path.join(self.DATA_DIR, filename)
        if not os.path.exists(path):
            return {} if filename.endswith(".json") else []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, filename, data):
        path = os.path.join(self.DATA_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_users(self):
        return self.load_json("users.json")

    def get_requests(self):
        return self.load_json("join_requests.json")

    def get_blocked_users(self):
        return self.load_json("blocked_users.json")

    def add_join_request(self, user_id: int, username: str):
        requests = self.get_requests()
        user_id_str = str(user_id)
        if user_id_str not in requests:
            requests[user_id_str] = {
                "username": username,
                "status": "pending"
            }
            self.save_json("join_requests.json", requests)



    async def approve_request(self, user_id, bot):
        requests = self.get_requests()
        users = self.get_users()
        user_id_str = str(user_id)

        if user_id_str in requests:
            request_info = requests[user_id_str]
            username = request_info.get("username") or request_info.get("name") or "Без имени"

            users[user_id_str] = {
                "username": username,
                "status": "approved",
                "joined": str(datetime.now().date())
            }
            del requests[user_id_str]
            self.save_json("users.json", users)
            self.save_json("join_requests.json", requests)

            try:
                await bot.send_message(
                    chat_id=int(user_id),
                    text="✅ Ваша заявка одобрена! Теперь вы можете использовать функционал бота."
                )
            except Exception as e:
                print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")


    def reject_request(self, user_id):
        requests = self.get_requests()
        blocked = self.get_blocked_users()
        user_id_str = str(user_id)
        user_id_int = int(user_id)

        if user_id_str in requests:
            del requests[user_id_str]
            self.save_json("join_requests.json", requests)

        if user_id_int not in blocked:
            blocked.append(user_id_int)
            self.save_json("blocked_users.json", blocked)


    def unblock_user(self, user_id):
        blocked = self.get_blocked_users()
        user_id = int(user_id)
        if user_id in blocked:
            blocked.remove(user_id)
            self.save_json("blocked_users.json", blocked)

    def get_users_list_text(self):
        users = self.get_users()
        if not users:
            return "Пользователей нет."
        lines = []
        for uid, info in users.items():
            name = info.get("username") or info.get("name") or "Без имени"
            status = info.get("status", "участник")
            lines.append(f"{uid} — {name} ({status})")
        return "\n".join(lines)

    def get_requests_keyboard(self):
        requests = self.get_requests()
        if not requests:
            return "Заявок нет.", None
        text_lines = []
        keyboard = []
        for uid, info in requests.items():
            name = info.get("username") or info.get("name") or "Без имени"
            text_lines.append(f"{uid} — {name}")
            keyboard.append([
                InlineKeyboardButton("Одобрить", callback_data=f"approve_request_{uid}"),
                InlineKeyboardButton("Отклонить", callback_data=f"reject_request_{uid}")
            ])
        return "\n".join(text_lines), InlineKeyboardMarkup(keyboard)

    def get_blocked_users_text(self):
        blocked = self.get_blocked_users()
        if not blocked:
            return "Заблокированных пользователей нет."
        return "\n".join([str(uid) for uid in blocked])

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids
    
    def is_approved(self, user_id: int) -> bool:
        users = self.get_users()
        user = users.get(str(user_id))
        return user is not None and user.get("status") == "approved"

