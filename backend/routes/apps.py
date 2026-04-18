import uuid
import secrets
from fastapi import APIRouter, HTTPException
from firebase_admin import firestore
from database import db
from schemas import AppCreateRequest, AppDeleteRequest, WebhookSaveRequest

router = APIRouter(tags=["Apps"])

@router.post("/apps/create")
def create_app(data: AppCreateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller_doc = next(seller_query, None)
    
    if not seller_doc: raise HTTPException(status_code=404, detail="Seller not found")
    
    seller_data = seller_doc.to_dict()
    is_premium = seller_data.get('is_premium', False)
    coins = seller_data.get('coins', 0)
    
    # --- OPTIMIZATION START: Server-side Count ---
    # Instead of downloading all apps, we ask Firebase to just send the number
    aggregate_query = db.collection('applications').where('ownerid', '==', data.ownerid).count()
    results = aggregate_query.get()
    current_apps_count = results[0][0].value
    # --- OPTIMIZATION END ---
    
    if not is_premium:
        if current_apps_count >= 2: raise HTTPException(status_code=400, detail="Free Tier Limit: Max 2 Apps.")
        if coins < 100: raise HTTPException(status_code=400, detail="Insufficient Coins. Need 100 coins.")
        seller_doc.reference.update({'coins': coins - 100})
    
    appid = str(uuid.uuid4())
    app_secret = secrets.token_hex(16)
    
    db.collection('applications').add({
        'appid': appid,
        'app_secret': app_secret,
        'name': data.app_name,
        'ownerid': data.ownerid,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    
    return {"status": "success", "appid": appid, "app_secret": app_secret}

@router.post("/apps/list")
def list_apps(data: dict):
    ownerid = data.get("ownerid")
    apps_ref = db.collection('applications').where('ownerid', '==', ownerid).stream()
    apps_list = []
    for doc in apps_ref:
        d = doc.to_dict()
        apps_list.append({
            "name": d['name'], 
            "appid": d['appid'], 
            "app_secret": d['app_secret'],
            "webhook_config": d.get('webhook_config', {}) 
        })
    return {"status": "success", "apps": apps_list}

@router.post("/apps/delete")
def delete_app(data: AppDeleteRequest):
    # 1. Find the app
    apps = db.collection('applications').where('appid', '==', data.appid).limit(1).stream()
    app_doc = next(apps, None)
    
    if not app_doc:
        raise HTTPException(status_code=404, detail="App not found")

    # 2. Batch Delete Users (Much faster)
    batch = db.batch()
    users = db.collection('users').where('appid', '==', data.appid).stream()
    count = 0
    
    for u in users:
        batch.delete(u.reference)
        count += 1
        # Firestore batch limit is 500
        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0
            
    # Delete remaining users and the app itself
    batch.delete(app_doc.reference)
    batch.commit()
    
    return {"status": "success"}

@router.post("/apps/webhook/save")
def save_webhook(data: WebhookSaveRequest):
    apps = db.collection('applications').where('appid', '==', data.appid).limit(1).stream()
    found = False
    for a in apps:
        a.reference.update({
            'webhook_config': {
                'url': data.webhook_url,
                'enabled': data.enabled,
                'show_hwid': data.show_hwid,
                # 'show_ip': data.show_ip,  <-- REMOVED
                'show_app': data.show_app,
                'show_expiry': data.show_expiry
            }
        })
        found = True
    if found: return {"status": "success"}
    raise HTTPException(status_code=404, detail="App not found")
