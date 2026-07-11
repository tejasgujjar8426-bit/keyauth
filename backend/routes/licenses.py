from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from database import db
from schemas import (
    LicenseCreateRequest,
    LicenseListRequest,
    LicenseDeleteRequest,
    LicenseActionRequest,
    ApiLicenseLoginRequest
)
from utils import send_discord_webhook, log_err

router = APIRouter(tags=["Licenses"])

@router.post("/licenses/create")
def create_license(data: LicenseCreateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller_doc = next(seller_query, None)
    if not seller_doc:
        seller_doc = db.collection('sellers').document(data.ownerid).get()
        if not seller_doc.exists:
            raise HTTPException(status_code=404, detail="Seller error: not found")

    dupes = db.collection('licenses').where('appid', '==', data.appid).where('license_key', '==', data.license_key).limit(1).stream()
    for _ in dupes:
        raise HTTPException(status_code=400, detail="License key already exists")

    if data.expire_str:
        expires = datetime.strptime(data.expire_str, "%Y-%m-%dT%H:%M")
    elif data.days == 0:
        expires = datetime(9999, 12, 31)
    else:
        expires = datetime.now() + timedelta(days=data.days)

    db.collection('licenses').add({
        'appid': data.appid,
        'license_key': data.license_key,
        'expires_at': expires.isoformat(),
        'hwid': None,
        'hwid_locked': False
    })
    return {"status": "success"}

@router.post("/licenses/list")
def list_licenses(data: LicenseListRequest):
    licenses = db.collection('licenses').where('appid', '==', data.appid).stream()
    l_list = [{"id": d.id, **d.to_dict()} for d in licenses]
    return {"status": "success", "licenses": l_list}

@router.post("/licenses/delete")
def delete_license(data: LicenseDeleteRequest):
    db.collection('licenses').document(data.license_id).delete()
    return {"status": "success"}

@router.post("/licenses/action")
def license_action(data: LicenseActionRequest):
    doc_ref = db.collection('licenses').document(data.license_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="License not found")
    updates = {}
    if data.action == "reset_hwid":
        updates['hwid'] = None
    elif data.action == "toggle_lock":
        updates['hwid_locked'] = data.lock_state
    elif data.action == "set_expiry":
        if data.expire_str:
            updates['expires_at'] = data.expire_str
    if updates:
        doc_ref.update(updates)
        return {"status": "success"}
    return {"status": "no_change"}

@router.post("/api/1.0/license_login")
async def license_login(data: ApiLicenseLoginRequest, request: Request, bg_tasks: BackgroundTasks):
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).where('app_secret', '==', data.app_secret).limit(1).stream()
    app_doc_ref = next(apps, None)
    if not app_doc_ref:
        return {"success": False, "message": "Invalid application details."}
    app_data = app_doc_ref.to_dict()

    licenses = db.collection('licenses').where('license_key', '==', data.license_key).where('appid', '==', app_data['appid']).limit(1).stream()
    lic_doc = next(licenses, None)
    if lic_doc is None:
        return {"success": False, "message": "Invalid license key."}
    l_data = lic_doc.to_dict()

    try:
        expiry_date = datetime.fromisoformat(l_data['expires_at'])
        if datetime.now() > expiry_date:
            return {"success": False, "message": "License has expired."}
    except Exception as e:
        log_err(f"License expiry check error: {e}")
        return {"success": False, "message": "Error verifying license status."}

    is_hwid_locked = l_data.get('hwid_locked', False)
    if is_hwid_locked:
        if l_data.get('hwid') is None:
            lic_doc.reference.update({'hwid': data.hwid})
            l_data['hwid'] = data.hwid
        elif l_data['hwid'] != data.hwid:
            return {"success": False, "message": "HWID mismatch."}
    else:
        lic_doc.reference.update({'hwid': data.hwid})
        l_data['hwid'] = data.hwid

    wh_config = app_data.get('webhook_config', {})
    if wh_config.get('enabled') and wh_config.get('url'):
        x_forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.client.host
        u_data_mapped = {
            'username': f"License: {data.license_key[:8]}...",
            'expires_at': l_data['expires_at'],
            'hwid': l_data['hwid']
        }
        bg_tasks.add_task(send_discord_webhook, wh_config['url'], u_data_mapped, wh_config, app_data['name'], client_ip)

    return {"success": True, "message": "Login successful.", "info": {"expires": l_data['expires_at']}}
