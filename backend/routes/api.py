from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Request
from database import db
from schemas import ApiLoginRequest
from utils import send_discord_webhook, log_err, parse_expiry

router = APIRouter(tags=["API"])

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list): return res[0][0].value
        return res[0].value
    except Exception: return 0

@router.post("/api/1.0/user_login")
async def user_login(data: ApiLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref: return {"success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()

    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).get()
    if not seller_query:
        return {"success": False, "message": "Invalid developer account."}
    seller_doc = seller_query[0]
    seller_data = seller_doc.to_dict()
    group = seller_data.get('seller_group', 0)
    plan_expires_at = seller_data.get('plan_expires_at')
    if plan_expires_at:
        try:
            expiry_date = datetime.fromisoformat(plan_expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry_date:
                seller_doc.reference.update({'seller_group': 0, 'plan_expires_at': None})
                group = 0
        except Exception:
            pass
    if group == 0:
        user_agg = db.collection('users').where('appid', '==', app_data['appid']).count()
        user_count = get_secure_count(user_agg)
        if user_count > 12:
            return {"success": False, "message": "Developer limit exceeded. Authentication suspended."}
    elif group == 1:
        user_agg = db.collection('users').where('appid', '==', app_data['appid']).count()
        user_count = get_secure_count(user_agg)
        if user_count > 24:
            return {"success": False, "message": "Developer limit exceeded. Authentication suspended."}

    # load user
    users = db.collection('users').where('username', '==', data.username).where('appid', '==', app_data['appid']).limit(1).stream()
    user_doc = next(users, None)
    if user_doc is None: return {"success": False, "message": "Invalid credentials."}
    
    u_data = user_doc.to_dict()
    if u_data['password'] != data.password: return {"success": False, "message": "Invalid credentials."}

    try:
        expiry_date = parse_expiry(u_data['expires_at'])
        
        if datetime.now(timezone.utc) > expiry_date:
            return {"success": False, "message": "Key expired."}
    except Exception as e:
        log_err(f"Expiry check error: {e}")
        return {"success": False, "message": "Error verifying subscription status."}
    
    u_data = user_doc.to_dict()
    if u_data['password'] != data.password: return {"success": False, "message": "Invalid credentials."}
    
    is_hwid_locked = u_data.get('hwid_locked', True)

    if is_hwid_locked:
        if u_data.get('hwid') is None:
            user_doc.reference.update({'hwid': data.hwid})
            u_data['hwid'] = data.hwid 
        elif u_data['hwid'] != data.hwid:
            return {"success": False, "message": "HWID mismatch."}
    else:
        user_doc.reference.update({'hwid': data.hwid})
        u_data['hwid'] = data.hwid
    
    wh_config = app_data.get('webhook_config', {})
    if wh_config.get('enabled') and wh_config.get('url'):
        x_forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.client.host
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data, wh_config, app_data['name'], client_ip)

    return {"success": True, "message": "Login successful.", "info": {"expires": u_data['expires_at']}}
