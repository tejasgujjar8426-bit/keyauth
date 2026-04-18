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
    
    # Fallback: Check if ownerid was used as Document ID manually
    if not seller_doc:
        seller_doc = db.collection('sellers').document(data.ownerid).get()
        if not seller_doc.exists:
            raise HTTPException(status_code=404, detail=f"Seller {data.ownerid} not found")
    
    seller_data = seller_doc.to_dict()
    group = seller_data.get('seller_group', 0)
    coins = seller_data.get('coins', 0)
    
    # 1. Check Apps Limit
    try:
        aggregate_query = db.collection('applications').where('ownerid', '==', data.ownerid).count()
        current_apps_count = aggregate_query.get()[0].value
    except Exception as e:
        print(f"Aggregation Error: {e}")
        current_apps_count = 0 # Fallback safety

    if group == 0 and current_apps_count >= 2:
        raise HTTPException(status_code=400, detail="Free Developer Limit: Max 2 Apps. Upgrade to Silver or Gold for more!")
    elif group == 1 and current_apps_count >= 10:
        raise HTTPException(status_code=400, detail="Silver Developer Limit: Max 10 Apps. Upgrade to Gold for unlimited apps!")

    # 2. Handle Coin Deduction
    if group == 0:
        if coins < 100: raise HTTPException(status_code=400, detail="Free Developer: Need 100 coins to create an app.")
        seller_doc.reference.update({'coins': coins - 100})
    elif group == 1:
        if coins < 50: raise HTTPException(status_code=400, detail="Silver Developer: Need 50 coins to create an app.")
        seller_doc.reference.update({'coins': coins - 50})
    # Group 2 (Gold) is free and unlimited
    
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
