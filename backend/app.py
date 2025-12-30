import uuid
import secrets
import os
import sys
import requests
import json
import httpx
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore

# --- COLOR LOGGING ---
def log_info(msg): print(f"\033[94m[INFO]\033[0m {msg}")
def log_success(msg): print(f"\033[92m[SUCCESS]\033[0m {msg}")
def log_warn(msg): print(f"\033[93m[WARNING]\033[0m {msg}")
def log_err(msg): print(f"\033[91m[ERROR]\033[0m {msg}")

# --- FIREBASE SETUP ---
# --- FIREBASE SETUP ---
service_account_info = os.getenv("SERVICE_ACCOUNT_JSON")

if not service_account_info:
    log_err("SERVICE_ACCOUNT_JSON environment variable NOT FOUND!")
    sys.exit(1)

try:
    # Parse the string from the environment variable into a dictionary
    cred_dict = json.loads(service_account_info)
    cred = credentials.Certificate(cred_dict)
    
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    log_success("Connected to Firebase Firestore!")
except Exception as e:
    log_err(f"Failed to connect to Firebase: {e}")
    sys.exit(1)

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- MODELS ---
class SellerSyncRequest(BaseModel): firebase_uid: str; email: str
class SellerDeleteRequest(BaseModel): ownerid: str
class AppCreateRequest(BaseModel): ownerid: str; app_name: str
class AppDeleteRequest(BaseModel): appid: str
class EndUserCreateRequest(BaseModel): ownerid: str; appid: str; username: str; password: str; days: int; expire_str: str = None
class ApiLoginRequest(BaseModel): ownerid: str; app_secret: str; username: str; password: str; hwid: str
class UserListRequest(BaseModel): appid: str
class UserDeleteRequest(BaseModel): user_id: str
class UserExtendRequest(BaseModel): user_id: str; days: int
class WebhookSaveRequest(BaseModel): 
    appid: str
    webhook_url: str
    enabled: bool
    show_hwid: bool
    show_ip: bool
    show_app: bool
    show_expiry: bool


async def send_discord_webhook(url, user_data, config, app_name, ip_address):
    if not url:
        return

    fields = []
    fields.append({"name": "User", "value": f"`{user_data['username']}`", "inline": True})

    if config.get('show_app'):
        fields.append({"name": "Application", "value": f"`{app_name}`", "inline": True})

    if config.get('show_hwid') and user_data.get('hwid'):
        fields.append({"name": "HWID", "value": f"```{user_data['hwid']}```", "inline": False})

    if config.get('show_expiry'):
        exp = user_data.get('expires_at', 'N/A').split('T')[0]
        fields.append({"name": "Expiry Date", "value": f"`{exp}`", "inline": True})

    if config.get('show_ip'):
        fields.append({"name": "IP Address", "value": f"`{ip_address}`", "inline": True})

    embed = {
        "title": "Login Authenticated",
        "color": 65280,
        "fields": fields,
        "footer": {"text": "Lynx Auth System"},
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        # Use httpx for non-blocking request
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"embeds": [embed]}, timeout=5)
        log_info(f"Webhook sent successfully for user: {user_data['username']}")
    except Exception as e:
        log_err(f"Failed to send webhook: {e}")

# --- API ENDPOINTS ---

@app.post("/auth/sync")
def sync_seller(data: SellerSyncRequest):
    print(f"\n--- SYNC REQUEST: {data.email} ({data.firebase_uid}) ---")
    
    doc_ref = db.collection('sellers').document(data.firebase_uid)
    doc = doc_ref.get()
    
    if doc.exists:
        existing_id = doc.to_dict().get('ownerid')
        log_success(f"FOUND EXISTING SELLER. OwnerID: {existing_id}")
        return {"status": "success", "ownerid": existing_id}
    else:
        log_warn("SELLER NOT FOUND. Creating NEW account...")
        new_ownerid = str(uuid.uuid4())
        doc_ref.set({
            'email': data.email,
            'ownerid': new_ownerid,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        log_success(f"Created New Seller. OwnerID: {new_ownerid}")
        return {"status": "success", "ownerid": new_ownerid}

@app.post("/apps/create")
def create_app(data: AppCreateRequest):
    log_info(f"Creating App '{data.app_name}' for Owner: {data.ownerid}")
    appid = str(uuid.uuid4())
    app_secret = secrets.token_hex(16)
    
    db.collection('applications').add({
        'appid': appid,
        'app_secret': app_secret,
        'name': data.app_name,
        'ownerid': data.ownerid,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    log_success(f"App Saved! ID: {appid}")
    return {"status": "success", "appid": appid, "app_secret": app_secret}

@app.post("/apps/list")
def list_apps(data: dict):
    ownerid = data.get("ownerid")
    log_info(f"Listing apps for Owner: {ownerid}")
    
    apps_ref = db.collection('applications').where('ownerid', '==', ownerid).stream()
    apps_list = []
    for doc in apps_ref:
        d = doc.to_dict()
        # EDITED: Added webhook_config to response
        apps_list.append({
            "name": d['name'], 
            "appid": d['appid'], 
            "app_secret": d['app_secret'],
            "webhook_config": d.get('webhook_config', {}) 
        })
    
    log_success(f"Found {len(apps_list)} apps.")
    return {"status": "success", "apps": apps_list}

@app.post("/apps/delete")
def delete_app(data: AppDeleteRequest):
    log_warn(f"Deleting App: {data.appid}")
    apps = db.collection('applications').where('appid', '==', data.appid).limit(1).stream()
    found = False
    for a in apps:
        a.reference.delete()
        found = True
    
    if found:
        # Delete users
        users = db.collection('users').where('appid', '==', data.appid).stream()
        for u in users: u.reference.delete()
        log_success("App and Users Deleted.")
        return {"status": "success"}
    
    raise HTTPException(status_code=404, detail="App not found")

@app.post("/users/create")
def create_end_user(data: EndUserCreateRequest):
    log_info(f"Creating User: {data.username}")
    
    # Check duplicate
    dupes = db.collection('users').where('appid', '==', data.appid).where('username', '==', data.username).limit(1).stream()
    for _ in dupes:
        log_err("Username exists!")
        raise HTTPException(status_code=400, detail="Username exists")

    if data.expire_str:
        # Parse the datetime-local HTML input format
        expires = datetime.strptime(data.expire_str, "%Y-%m-%dT%H:%M")
    elif data.days == 0: 
        expires = datetime(9999, 12, 31)
    else: 
        expires = datetime.utcnow() + timedelta(days=data.days)

    db.collection('users').add({
        'appid': data.appid,
        'username': data.username,
        'password': data.password,
        'expires_at': expires.isoformat(),
        'hwid': None
    })
    log_success("User Created.")
    return {"status": "success"}

@app.post("/users/list")
def list_users(data: UserListRequest):
    log_info(f"Fetching users for App: {data.appid}")
    users = db.collection('users').where('appid', '==', data.appid).stream()
    u_list = [{"id": d.id, **d.to_dict()} for d in users]
    return {"status": "success", "users": u_list}

@app.post("/users/delete")
def delete_user(data: UserDeleteRequest):
    db.collection('users').document(data.user_id).delete()
    return {"status": "success"}

@app.post("/api/1.0/user_login")
async def user_login(data: ApiLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    log_info(f"Login Attempt: {data.username} (HWID: {data.hwid})")
    
    # 1. Find App
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    
    if not app_doc_ref:
        return {"success": False, "message": "Invalid application details."}

    app_data = app_doc_ref.to_dict()

    # 2. Find User
    users = db.collection('users').where('username', '==', data.username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    
    if not user_doc:
        return {"success": False, "message": "Invalid credentials."}
    
    u_data = user_doc.to_dict()
    if u_data['password'] != data.password:
        return {"success": False, "message": "Invalid credentials."}
        
    # 3. HWID Lock
    if u_data.get('hwid') is None:
        user_doc.reference.update({'hwid': data.hwid})
        u_data['hwid'] = data.hwid # Update local for webhook
    elif u_data['hwid'] != data.hwid:
        return {"success": False, "message": "HWID mismatch."}
    
    # --- WEBHOOK TRIGGER ---
    wh_config = app_data.get('webhook_config')
    if wh_config and wh_config.get('enabled') and wh_config.get('url'):
        # FIX: Get the correct client IP on Render
        x_forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.client.host
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data, wh_config, app_data['name'], client_ip)
    # -----------------------

    return {"success": True, "message": "Login successful.", "info": {"expires": u_data['expires_at']}}


@app.post("/seller/delete")
def delete_seller(data: SellerDeleteRequest):
    log_warn(f"DELETING SELLER: {data.ownerid}")
    db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).get()[0].reference.delete()
    
    # Clean apps
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).stream()
    for a in apps:
        # Clean users
        users = db.collection('users').where('appid', '==', a.get('appid')).stream()
        for u in users: u.reference.delete()
        a.reference.delete()
        
    return {"status": "success"}

@app.post("/apps/webhook/save")
def save_webhook(data: WebhookSaveRequest):
    log_info(f"Updating Webhook for App: {data.appid}")
    
    apps = db.collection('applications').where('appid', '==', data.appid).limit(1).stream()
    found = False
    for a in apps:
        a.reference.update({
            'webhook_config': {
                'url': data.webhook_url,
                'enabled': data.enabled,
                'show_hwid': data.show_hwid,
                'show_ip': data.show_ip,
                'show_app': data.show_app,
                'show_expiry': data.show_expiry
            }
        })
        found = True
    
    if found: return {"status": "success"}
    raise HTTPException(status_code=404, detail="App not found")



