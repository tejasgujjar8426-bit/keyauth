import os
import secrets
from fastapi import APIRouter, HTTPException
from database import db
from schemas import (
    AdminSearchRequest, 
    AdminUpdateRequest, 
    AdminPublishUpdate,
    AdminVerifyRequest,
    AdminSellersRequest,
    AdminUsersRequest,
    AdminCodesRequest,
    AdminCodeGenerateRequest,
    AdminCleanRequest,
    AdminCodeActionRequest
)
from datetime import datetime

router = APIRouter(tags=["Admin"])

try:
    if os.path.exists("admin_Secret.txt"):
        with open("admin_Secret.txt", "r") as f:
            ADMIN_SECRET = f.read().strip()
    elif os.path.exists("../admin_Secret.txt"):
        with open("../admin_Secret.txt", "r") as f:
            ADMIN_SECRET = f.read().strip()
    else:
        ADMIN_SECRET = "lynx_admin_secret"
except Exception:
    ADMIN_SECRET = "lynx_admin_secret"

def get_secure_count(agg):
    try:
        res = agg.get()
        if isinstance(res[0], list):
            return res[0][0].value
        return res[0].value
    except Exception:
        return 0

@router.post("/admin/stats")
def get_admin_stats(data: AdminVerifyRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    sellers_count = get_secure_count(db.collection('sellers').count())
    users_count = get_secure_count(db.collection('users').count())
    silver_count = get_secure_count(db.collection('sellers').where('seller_group', '==', 1).count())
    gold_count = get_secure_count(db.collection('sellers').where('seller_group', '==', 2).count())
    apps_count = get_secure_count(db.collection('applications').count())
    return {
        "status": "success",
        "sellers": sellers_count,
        "users": users_count,
        "gold": gold_count,
        "silver": silver_count,
        "apps": apps_count 
    }

@router.post("/admin/verify")
def verify_admin(data: AdminVerifyRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return {"status": "success"}

@router.post("/admin/sellers")
def list_sellers(data: AdminSellersRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    sellers = db.collection('sellers').stream()
    s_list = []
    for s in sellers:
        d = s.to_dict()
        app_agg = db.collection('applications').where('ownerid', '==', d.get('ownerid')).count()
        app_count = get_secure_count(app_agg)
        s_list.append({
            "email": d.get("email"),
            "ownerid": d.get("ownerid"),
            "coins": d.get("coins", 0),
            "seller_group": d.get("seller_group", 0),
            "plan_expires_at": d.get("plan_expires_at"),
            "app_count": app_count
        })
    return {"status": "success", "sellers": s_list}

@router.post("/admin/users")
def list_users(data: AdminUsersRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    users = db.collection('users').stream()
    u_list = []
    apps_cache = {}
    apps = db.collection('applications').stream()
    for app in apps:
        ad = app.to_dict()
        apps_cache[ad['appid']] = {"name": ad['name'], "ownerid": ad['ownerid']}
    sellers_cache = {}
    sellers = db.collection('sellers').stream()
    for sel in sellers:
        sd = sel.to_dict()
        sellers_cache[sd['ownerid']] = sd.get('email')
    for u in users:
        ud = u.to_dict()
        appid = ud.get("appid")
        app_info = apps_cache.get(appid, {"name": "Unknown App", "ownerid": None})
        owner_email = sellers_cache.get(app_info["ownerid"], "Unknown Seller")
        u_list.append({
            "id": u.id,
            "username": ud.get("username"),
            "password": ud.get("password"),
            "appid": appid,
            "app_name": app_info["name"],
            "owner_email": owner_email,
            "expires_at": ud.get("expires_at"),
            "hwid": ud.get("hwid"),
            "hwid_locked": ud.get("hwid_locked", True)
        })
    return {"status": "success", "users": u_list}

@router.post("/admin/codes")
def list_codes(data: AdminCodesRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    codes = db.collection('gift_codes').stream()
    c_list = [{"id": c.id, **c.to_dict()} for c in codes]
    return {"status": "success", "codes": c_list}

@router.post("/admin/generate_code")
def generate_code(data: AdminCodeGenerateRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    code_str = "LYNX-" + "-".join("".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(4)) for _ in range(3))
    db.collection('gift_codes').add({
        "code": code_str,
        "tier": data.tier,
        "duration_days": data.duration_days,
        "max_uses": data.max_uses,
        "use_count": 0,
        "used": False,
        "used_by": None,
        "used_at": None,
        "created_at": datetime.now().isoformat()
    })
    return {"status": "success", "code": code_str}

@router.post("/admin/clean_ghost_data")
def clean_ghost_data(data: AdminCleanRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    sellers = db.collection('sellers').stream()
    seller_ids = {s.to_dict().get("ownerid") for s in sellers if s.to_dict().get("ownerid")}
    apps = db.collection('applications').stream()
    app_ids = set()
    apps_to_delete = []
    for app in apps:
        ad = app.to_dict()
        if ad.get("ownerid") not in seller_ids:
            apps_to_delete.append(app.reference)
        else:
            app_ids.add(ad.get("appid"))
    for ref in apps_to_delete:
        ref.delete()
    users = db.collection('users').stream()
    users_to_delete = []
    for u in users:
        ud = u.to_dict()
        if ud.get("appid") not in app_ids:
            users_to_delete.append(u.reference)
    for ref in users_to_delete:
        ref.delete()
    licenses = db.collection('licenses').stream()
    licenses_to_delete = []
    for l in licenses:
        ld = l.to_dict()
        if ld.get("appid") not in app_ids:
            licenses_to_delete.append(l.reference)
    for ref in licenses_to_delete:
        ref.delete()
    return {
        "status": "success",
        "cleaned_apps": len(apps_to_delete),
        "cleaned_users": len(users_to_delete),
        "cleaned_licenses": len(licenses_to_delete)
    }

@router.post("/admin/search_seller")
def admin_search(data: AdminSearchRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    if not seller:
        seller = db.collection('sellers').document(data.ownerid).get()
        if not seller.exists:
            return {"status": "success", "found": False}
    d = seller.to_dict()
    app_agg = db.collection('applications').where('ownerid', '==', d.get('ownerid')).count()
    app_count = get_secure_count(app_agg)
    return {
        "status": "success",
        "found": True,
        "data": {
            "email": d.get('email'),
            "ownerid": d.get('ownerid'),
            "coins": d.get('coins', 0),
            "seller_group": d.get('seller_group', 0),
            "app_count": app_count 
        }
    }

@router.post("/admin/update_seller")
def admin_update(data: AdminUpdateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    if seller:
        seller.reference.update({
            "seller_group": data.seller_group
        })
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Seller not found")

@router.post("/admin/publish_update")
def publish_update(data: AdminPublishUpdate):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    update_ref = db.collection('updates').document()
    update_ref.set({
        "message": data.message,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": datetime.now().timestamp()
    })
    return {"status": "success", "message": "Update published!"}

@router.get("/public/updates")
def get_updates():
    updates_query = db.collection('updates').order_by('timestamp', direction='DESCENDING').limit(10).stream()
    updates = []
    for u in updates_query:
        updates.append(u.to_dict())
    return {"status": "success", "updates": updates}
@router.post("/admin/action_code")
def action_code(data: AdminCodeActionRequest):
    if data.secret_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")
    doc_ref = db.collection('gift_codes').document(data.code_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Code not found")
    if data.action == "delete":
        code_data = doc.to_dict()
        used_by = code_data.get("used_by")
        if used_by:
            seller_query = db.collection('sellers').where('ownerid', '==', used_by).limit(1).stream()
            seller = next(seller_query, None)
            if seller:
                seller.reference.update({'seller_group': 0, 'plan_expires_at': None})
        doc_ref.delete()
    elif data.action == "toggle_status":
        d = doc.to_dict()
        disabled = d.get("disabled", False)
        doc_ref.update({"disabled": not disabled})
    return {"status": "success"}

