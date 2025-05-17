import os
import json
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class Database:
    def __init__(self, data_dir="data", admin_user_ids=None):
        self.DATA_DIR = data_dir
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
        users = self.load_json("users.json")
        if str(user_id) not in users:
            users[str(user_id)] = {
                "username": username,
                "status": "pending"
            }
            self.save_json("users.json", users)

    def approve_request(self, user_id):
        requests = self.get_requests()
        users = self.get_users()
        user_id = str(user_id)

        if user_id in requests:
            users[user_id] = {
                "name": requests[user_id]["name"],
                "joined": str(datetime.now().date())
            }
            del requests[user_id]
            self.save_json("users.json", users)
            self.save_json("join_requests.json", requests)

    def reject_request(self, user_id):
        requests = self.get_requests()
        user_id = str(user_id)
        if user_id in requests:
            del requests[user_id]
            self.save_json("join_requests.json", requests)

    def block_user(self, user_id):
        blocked = self.get_blocked_users()
        user_id = int(user_id)
        if user_id not in blocked:
            blocked.append(user_id)
            self.save_json("blocked_users.json", blocked)

        users = self.get_users()
        users.pop(str(user_id), None)
        self.save_json("users.json", users)

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
