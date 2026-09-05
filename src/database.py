import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict

DB_PATH = Path("data/autonect.db")

def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn

def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            deepseek_url TEXT,
            name TEXT,
            pinned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT REFERENCES chats(id) ON DELETE CASCADE,
            role TEXT CHECK(role IN ('user', 'assistant')),
            content TEXT,
            thinking TEXT,
            commands_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)")
    conn.commit()

def upsert_chat(chat_id: str, deepseek_url: Optional[str] = None, name: Optional[str] = None, pinned: bool = False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM chats WHERE id = ?", (chat_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO chats (id, deepseek_url, name, pinned) VALUES (?, ?, ?, ?)",
            (chat_id, deepseek_url, name or f"Chat {chat_id[:8]}", 1 if pinned else 0)
        )
    else:
        updates = []
        params = []
        if deepseek_url is not None:
            updates.append("deepseek_url = ?")
            params.append(deepseek_url)
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if pinned is not None:
            updates.append("pinned = ?")
            params.append(1 if pinned else 0)
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(chat_id)
            cur.execute(f"UPDATE chats SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

def get_chat_list():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.name, c.pinned, c.deepseek_url, c.updated_at,
               (SELECT content FROM messages WHERE chat_id = c.id ORDER BY created_at DESC LIMIT 1) AS last_message
        FROM chats c
        ORDER BY c.pinned DESC, c.updated_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_chat(chat_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
    chat = cur.fetchone()
    if not chat:
        conn.close()
        return None
    cur.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC", (chat_id,))
    messages = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {**dict(chat), "messages": messages}

def update_chat(chat_id: str, name: Optional[str] = None, pinned: Optional[bool] = None):
    conn = get_db()
    cur = conn.cursor()
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if pinned is not None:
        updates.append("pinned = ?")
        params.append(1 if pinned else 0)
    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(chat_id)
        cur.execute(f"UPDATE chats SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()

def update_chat_name(chat_id: str, name: str):
    conn = get_db()
    conn.execute("UPDATE chats SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, chat_id))
    conn.commit()
    conn.close()

def delete_chat(chat_id: str):
    conn = get_db()
    conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()

def add_message(chat_id: str, role: str, content: str, thinking: Optional[str] = None, commands: Optional[List[Dict]] = None):
    conn = get_db()
    commands_json = json.dumps(commands) if commands else None
    conn.execute(
        "INSERT INTO messages (chat_id, role, content, thinking, commands_json) VALUES (?, ?, ?, ?, ?)",
        (chat_id, role, content, thinking, commands_json)
    )
    conn.execute("UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (chat_id,))
    conn.commit()
    conn.close()