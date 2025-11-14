import sqlite3
import uuid
import secrets
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from argon2 import PasswordHasher

# --- Setup ---
ph = PasswordHasher()
app = FastAPI()

# --- Database Path Configuration (For Render) ---
IS_ON_RENDER = os.environ.get('RENDER', False)
DB_PATH = os.path.join("/var/data", "platform_users.db") if IS_ON_RENDER else "platform_users.db"

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Database Initialization ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS sellers (username TEXT PRIMARY KEY, hashed_password TEXT NOT NULL, ownerid TEXT NOT NULL UNIQUE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS applications (appid TEXT PRIMARY KEY, app_secret TEXT NOT NULL UNIQUE, name TEXT NOT NULL, ownerid TEXT NOT NULL, FOREIGN KEY (ownerid) REFERENCES sellers (ownerid))")
        cursor.execute("CREATE TABLE IF NOT EXISTS end_users (id INTEGER PRIMARY KEY AUTOINCREMENT, appid TEXT NOT NULL, username TEXT NOT NULL, password TEXT NOT NULL, expires_at TEXT NOT NULL, hwid TEXT, UNIQUE(appid, username), FOREIGN KEY (appid) REFERENCES applications (appid))")
        conn.commit()

# --- Pydantic Models ---
class SellerAuthRequest(BaseModel): username: str; password: str
class AppCreateRequest(BaseModel): ownerid: str; app_name: str
class EndUserCreateRequest(BaseModel): ownerid: str; appid: str; username: str; password: str; days: int
class ApiLoginRequest(BaseModel): ownerid: str; app_secret: str; username: str; password: str; hwid: str
class UserListRequest(BaseModel): appid: str
class UserDeleteRequest(BaseModel): user_id: int
class UserExtendRequest(BaseModel): user_id: int; days: int

# --- Health Check Endpoint for UptimeRobot ---
@app.get("/health")
def health_check():
    return {"status": "ok"}

# --- Seller Panel API Endpoints ---
@app.post("/register")
def seller_register(data: SellerAuthRequest):
    # (Same as before)
    try:
        hashed_password = ph.hash(data.password)
        ownerid = str(uuid.uuid4())
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO sellers (username, hashed_password, ownerid) VALUES (?, ?, ?)", (data.username, hashed_password, ownerid))
            conn.commit()
        return {"status": "success"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Seller username already taken.")

@app.post("/login")
def seller_login(data: SellerAuthRequest):
    # (Same as before)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT hashed_password, ownerid FROM sellers WHERE username = ?", (data.username,))
        result = cursor.fetchone()
    if not result: raise HTTPException(status_code=404, detail="Seller not found.")
    hashed_password, ownerid = result
    try:
        ph.verify(hashed_password, data.password)
        return {"status": "success", "ownerid": ownerid}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid password.")

# ... (Other endpoints like /apps/create, /apps/list, /users/create are the same)
@app.post("/apps/create")
def create_app(data: AppCreateRequest):
    appid = str(uuid.uuid4()); app_secret = secrets.token_hex(16)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO applications (appid, app_secret, name, ownerid) VALUES (?, ?, ?, ?)", (appid, app_secret, data.app_name, data.ownerid))
        conn.commit()
    return {"status": "success", "appid": appid, "app_secret": app_secret}

@app.post("/apps/list")
def list_apps(data: dict):
    ownerid = data.get("ownerid")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name, appid, app_secret FROM applications WHERE ownerid = ?", (ownerid,))
        apps = [dict(row) for row in cursor.fetchall()]
    return {"status": "success", "apps": apps}
    
@app.post("/users/create")
def create_end_user(data: EndUserCreateRequest):
    if data.days == 0: expires_at = datetime(9999, 12, 31)
    else: expires_at = datetime.utcnow() + timedelta(days=data.days)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO end_users (appid, username, password, expires_at) VALUES (?, ?, ?, ?)", (data.appid, data.username, data.password, expires_at.isoformat()))
        conn.commit()
    return {"status": "success", "message": f"User '{data.username}' created."}


# --- User Management Endpoints ---
@app.post("/users/list")
def list_users(data: UserListRequest):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, expires_at FROM end_users WHERE appid = ?", (data.appid,))
        users = [dict(row) for row in cursor.fetchall()]
    return {"status": "success", "users": users}

@app.post("/users/delete")
def delete_user(data: UserDeleteRequest):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM end_users WHERE id = ?", (data.user_id,))
        conn.commit()
    return {"status": "success", "message": "User deleted."}

@app.post("/users/extend")
def extend_user(data: UserExtendRequest):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT expires_at FROM end_users WHERE id = ?", (data.user_id,))
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="User not found.")
        
        current_expiry = datetime.fromisoformat(result['expires_at'])
        
        # --- THIS IS THE FIX ---
        # If the year is 9999, they already have a lifetime key. Don't extend.
        if current_expiry.year == 9999:
            return {"status": "success", "message": "User already has a lifetime subscription.", "new_expiry": current_expiry.isoformat()}
        # --- END OF FIX ---

        base_date = max(datetime.utcnow(), current_expiry)
        new_expiry = base_date + timedelta(days=data.days)
        
        cursor.execute("UPDATE end_users SET expires_at = ? WHERE id = ?", (new_expiry.isoformat(), data.user_id))
        conn.commit()
    return {"status": "success", "new_expiry": new_expiry.isoformat()}

# --- PUBLIC API FOR CLIENT APPLICATIONS ---
@app.post("/api/1.0/user_login")
def user_login(data: ApiLoginRequest):
    # (Same as before)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT appid FROM applications WHERE ownerid = ? AND app_secret = ?", (data.ownerid, data.app_secret))
        app_data = cursor.fetchone()
        if not app_data: return {"success": False, "message": "Invalid application details."}
        cursor.execute("SELECT * FROM end_users WHERE username = ? AND appid = ?", (data.username, app_data["appid"]))
        user_data = cursor.fetchone()
        if not user_data or user_data["password"] != data.password: return {"success": False, "message": "Invalid credentials."}
        if datetime.fromisoformat(user_data["expires_at"]) < datetime.utcnow(): return {"success": False, "message": "Subscription has expired."}
        if user_data["hwid"] is None:
            cursor.execute("UPDATE end_users SET hwid = ? WHERE id = ?", (data.hwid, user_data["id"]))
            conn.commit()
        elif user_data["hwid"] != data.hwid: return {"success": False, "message": "HWID mismatch."}
    return {"success": True, "message": "Login successful.", "info": { "expires": user_data["expires_at"] }}

# --- Run DB Init ---
@app.on_event("startup")
def on_startup():
    init_db()
