from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Request
from database import db
from schemas import ApiLoginRequest
from utils import send_discord_webhook, log_err

router = APIRouter(tags=["API"])

@router.post("/api/1.0/user_login")
async def user_login(data: ApiLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    # 1. Fetch App
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref: return {"success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()

    # 2. Fetch User
    users = db.collection('users').where('username', '==', data.username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    if user_doc is None: return {"success": False, "message": "Invalid credentials."}
    
    u_data = user_doc.to_dict()
    if u_data['password'] != data.password: return {"success": False, "message": "Invalid credentials."}

    # --- ADD THIS EXPIRY CHECK HERE ---
    try:
        # Convert the stored ISO string back to a datetime object
        expiry_date = datetime.fromisoformat(u_data['expires_at'])
        
        # Compare with current UTC time
        if datetime.utcnow() > expiry_date:
            return {"success": False, "message": "Your subscription has expired."}
    except Exception as e:
        log_err(f"Expiry check error: {e}")
        return {"success": False, "message": "Error verifying subscription status."}
    
    u_data = user_doc.to_dict()
    if u_data['password'] != data.password: return {"success": False, "message": "Invalid credentials."}
    
    # --- NEW LOGIC: HWID LOCK ---
    # Default is TRUE (Locked) if the field doesn't exist
    is_hwid_locked = u_data.get('hwid_locked', True)

    if is_hwid_locked:
        # Standard Strict Logic
        if u_data.get('hwid') is None:
            user_doc.reference.update({'hwid': data.hwid})
            u_data['hwid'] = data.hwid 
        elif u_data['hwid'] != data.hwid:
            return {"success": False, "message": "HWID mismatch."}
    else:
        # Unlocked Logic: Allow anyone, but update DB so admin sees the current user's HWID
        user_doc.reference.update({'hwid': data.hwid})
        u_data['hwid'] = data.hwid
    
    # 3. Webhook (Unchanged)
    wh_config = app_data.get('webhook_config', {})
    if wh_config.get('enabled') and wh_config.get('url'):
        x_forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.client.host
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data, wh_config, app_data['name'], client_ip)

    return {"success": True, "message": "Login successful.", "info": {"expires": u_data['expires_at']}}
