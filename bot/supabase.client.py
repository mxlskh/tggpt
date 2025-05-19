from supabase import create_client, Client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Пример функций:

def get_approved_users():
    response = supabase.table("users").select("*").eq("status", "approved").execute()
    return response.data

def get_pending_requests():
    response = supabase.table("join_requests").select("*").execute()
    return response.data

def add_join_request(user_id: int, username: str):
    supabase.table("join_requests").insert({
        "user_id": user_id,
        "username": username
    }).execute()

def approve_user(user_id: int, username: str):
    # Добавляем в users
    supabase.table("users").insert({
        "user_id": user_id,
        "username": username,
        "status": "approved"
    }).execute()

    # Удаляем из join_requests
    supabase.table("join_requests").delete().eq("user_id", user_id).execute()

def reject_user(user_id: int):
    # Удаляем из join_requests
    supabase.table("join_requests").delete().eq("user_id", user_id).execute()
    
    # Добавляем в blocked_users
    supabase.table("blocked_users").insert({"user_id": user_id}).execute()

def is_blocked(user_id: int) -> bool:
    response = supabase.table("blocked_users").select("*").eq("user_id", user_id).execute()
    return len(response.data) > 0
