import os
import json
import time
import urllib.request
import urllib.error
import boto3

# ================== CONFIG ==================
BOT_TOKEN = os.environ["BOT_TOKEN"]
TG_SECRET = os.environ.get("TG_SECRET")

# --- ID ВАШЕЙ ГРУППЫ (ЖЕСТКО ПРОПИСАН) ---
ADMIN_CHAT_ID = "-000000000000"
# -----------------------------------------

# S3 SETTINGS
BUCKET_NAME = os.environ.get("BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
DB_FILE_KEY = "topics.json"

# ================== DEDUP & CACHE ==================
SEEN = {}
SEEN_TTL = 600
DB_CACHE = None

# ================== S3 DATABASE ==================
def get_s3_client():
    session = boto3.session.Session()
    return session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )

def load_db():
    global DB_CACHE
    if DB_CACHE is not None:
        return DB_CACHE
    s3 = get_s3_client()
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=DB_FILE_KEY)
        data = json.loads(obj['Body'].read())
        DB_CACHE = data
        return data
    except Exception:
        return {}

def save_db(data):
    global DB_CACHE
    DB_CACHE = data
    s3 = get_s3_client()
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=DB_FILE_KEY,
            Body=json.dumps(data, ensure_ascii=False, indent=2)
        )
    except Exception as e:
        print(f"S3 Save Error: {e}")

# ================== TELEGRAM API ==================
def tg_api(method: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{API_BASE}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return json.loads(err_body)
        except:
            return {"ok": False, "description": f"HTTP Error {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "description": f"Connection Error: {str(e)}"}


def send_message(chat_id, text, thread_id=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "Markdown" # Включаем Markdown для красивого ID
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    return tg_api("sendMessage", payload)

def forward_message(chat_id, from_chat_id, message_id, thread_id=None):
    payload = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    return tg_api("forwardMessage", payload)

def create_forum_topic(group_id, name):
    res = tg_api("createForumTopic", {
        "chat_id": group_id,
        "name": name
    })
    
    if not res or not res.get("ok"):
        error_text = json.dumps(res, ensure_ascii=False, indent=2)
        tg_api("sendMessage", {
            "chat_id": group_id,
            "text": f"🚨 ОШИБКА TGS:\n<pre>{error_text}</pre>",
            "parse_mode": "HTML"
        })
        return None

    return res["result"]["message_thread_id"]

# ================== SEND ANY MESSAGE (ADMIN -> USER) ==================
def send_any_message(target_chat_id, msg, target_thread_id=None):
    base_payload = {"chat_id": target_chat_id}
    if target_thread_id:
        base_payload["message_thread_id"] = target_thread_id

    if "text" in msg:
        base_payload["text"] = msg["text"]
        return tg_api("sendMessage", base_payload)
    
    if "photo" in msg:
        base_payload["photo"] = msg["photo"][-1]["file_id"]
        base_payload["caption"] = msg.get("caption")
        return tg_api("sendPhoto", base_payload)
        
    if "video" in msg:
        base_payload["video"] = msg["video"]["file_id"]
        base_payload["caption"] = msg.get("caption")
        return tg_api("sendVideo", base_payload)
        
    if "voice" in msg:
        base_payload["voice"] = msg["voice"]["file_id"]
        return tg_api("sendVoice", base_payload)

    if "document" in msg:
        base_payload["document"] = msg["document"]["file_id"]
        base_payload["caption"] = msg.get("caption")
        return tg_api("sendDocument", base_payload)
    
    if "sticker" in msg:
        base_payload["sticker"] = msg["sticker"]["file_id"]
        return tg_api("sendSticker", base_payload)

    return send_message(target_chat_id, "📎 Тип сообщения не поддерживается", target_thread_id)


# ================== HANDLER ==================
def _get_header(event, name: str):
    headers = event.get("headers") or {}
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None

def handler(event, context):
    if TG_SECRET:
        got = _get_header(event, "X-Telegram-Bot-Api-Secret-Token")
        if got != TG_SECRET:
            return {"statusCode": 401, "body": "unauthorized"}

    body = event.get("body") or "{}"
    try:
        update = json.loads(body)
    except:
        return {"statusCode": 200, "body": "ok"}

    update_id = update.get("update_id")
    if update_id:
        if str(update_id) in SEEN:
            return {"statusCode": 200, "body": "ok"}
        SEEN[str(update_id)] = int(time.time())

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return {"statusCode": 200, "body": "ok"}

    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "").strip()
    
    db = load_db()

    # --- ADMIN FLOW ---
    if str(chat_id) == str(ADMIN_CHAT_ID):
        thread_id = msg.get("message_thread_id")
        
        # КОМАНДЫ /RESET
        if text.lower().startswith("/reset"):
            parts = text.split()
            
            if len(parts) > 1 and parts[1] == "all":
                db = {}
                save_db(db)
                send_message(ADMIN_CHAT_ID, "💥 База полностью очищена.", thread_id)
                return {"statusCode": 200, "body": "ok"}
            
            if len(parts) > 1:
                target_id = parts[1]
                if target_id in db:
                    del db[target_id]
                    save_db(db)
                    send_message(ADMIN_CHAT_ID, f"✅ Юзер {target_id} забыт.", thread_id)
                else:
                    send_message(ADMIN_CHAT_ID, "⚠️ ID не найден.", thread_id)
                return {"statusCode": 200, "body": "ok"}

            if thread_id:
                user_to_reset = None
                for uid, tid in db.items():
                    if str(tid) == str(thread_id):
                        user_to_reset = uid
                        break
                
                if user_to_reset:
                    del db[user_to_reset]
                    save_db(db)
                    send_message(ADMIN_CHAT_ID, "♻️ Привязка сброшена.", thread_id)
                else:
                    send_message(ADMIN_CHAT_ID, "⚠️ Топик не найден в базе.", thread_id)
            else:
                send_message(ADMIN_CHAT_ID, "ℹ️ Пишите `/reset` внутри темы.", thread_id)
            
            return {"statusCode": 200, "body": "ok"}

        # ОБЫЧНЫЙ ОТВЕТ АДМИНА
        if not thread_id:
            return {"statusCode": 200, "body": "ok"}

        target_user = None
        for uid, tid in db.items():
            if str(tid) == str(thread_id):
                target_user = uid
                break
        
        if target_user:
            send_any_message(target_user, msg)
            
        return {"statusCode": 200, "body": "ok"}

    # --- USER FLOW (НОВАЯ ЛОГИКА) ---
    if msg.get("chat", {}).get("type") == "private":
        user_data = msg.get("from", {})
        user_id = str(user_data.get("id"))
        
        # Получаем данные
        raw_username = user_data.get("username")
        raw_first = user_data.get("first_name")
        raw_last = user_data.get("last_name")

        # Формируем строки для отчета (с "нет" если пусто)
        disp_username = f"@{raw_username}" if raw_username else "нет"
        disp_first = raw_first if raw_first else "нет"
        disp_last = raw_last if raw_last else "нет"

        topic_id = db.get(user_id)
        
        # Если темы нет — создаем новую
        if not topic_id:
            
            # --- ЛОГИКА НАЗВАНИЯ ТЕМЫ ---
            if raw_username:
                # Если есть юзернейм: "@elofey (123...)"
                topic_name = f"@{raw_username} ({user_id})"
            else:
                # Если нет: "Иван (123...)"
                # (Если вдруг и имени нет, будет "User")
                clean_name = raw_first if raw_first else "User"
                topic_name = f"{clean_name} ({user_id})"

            # Обрезаем, чтобы не превысить лимит ТГ
            topic_name = topic_name[:60]

            topic_id = create_forum_topic(ADMIN_CHAT_ID, topic_name)
            
            if topic_id:
                db[user_id] = topic_id
                save_db(db)
                
                # --- ЛОГИКА ПЕРВОГО СООБЩЕНИЯ ---
                info_text = (
                    f"🟢 Новый чат с:\n"
                    f"Юзернейм: {disp_username}\n"
                    f"Имя: {disp_first}\n"
                    f"Фамилия: {disp_last}\n"
                    f"ID: `{user_id}`"
                )
                
                send_message(ADMIN_CHAT_ID, info_text, topic_id)
            else:
                return {"statusCode": 200, "body": "ok"}

        # ПЕРЕСЫЛАЕМ сообщение в топик
        forward_message(
            chat_id=ADMIN_CHAT_ID, 
            from_chat_id=chat_id, 
            message_id=msg["message_id"], 
            thread_id=topic_id
        )

    return {"statusCode": 200, "body": "ok"}
