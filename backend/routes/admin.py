from fastapi import APIRouter, HTTPException
from database import db
from schemas import AdminSearchRequest, AdminUpdateRequest, AdminPublishUpdate
from datetime import datetime

router = APIRouter(tags=["Admin"])

@router.post("/admin/stats")
def get_admin_stats():
    # Count Total Sellers
    sellers_agg = db.collection('sellers').count()
    sellers_count = sellers_agg.get()[0].value

    # Count Total End Users
    users_agg = db.collection('users').count()
    users_count = users_agg.get()[0].value

    # Count Groups
    plus_agg = db.collection('sellers').where('seller_group', '==', 1).count()
    prem_agg = db.collection('sellers').where('seller_group', '==', 2).count()
    plus_count = plus_agg.get()[0].value
    prem_count = prem_agg.get()[0].value

    # --- NEW: Count Total Apps ---
    apps_agg = db.collection('applications').count()
    apps_count = apps_agg.get()[0].value

    return {
        "status": "success",
        "sellers": sellers_count,
        "users": users_count,
        "premium": prem_count,
        "plus": plus_count,
        "apps": apps_count 
    }

@router.post("/admin/search_seller")
def admin_search(data: AdminSearchRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    
    if seller:
        d = seller.to_dict()
        
        app_agg = db.collection('applications').where('ownerid', '==', data.ownerid).count()
        app_count = app_agg.get()[0].value

        return {
            "status": "success",
            "found": True,
            "data": {
                "email": d.get('email'),
                "ownerid": d.get('ownerid'),
                "coins": d.get('coins', 0),
                "is_premium": d.get('is_premium', False),
                "seller_group": d.get('seller_group', 2 if d.get('is_premium') else 0),
                "app_count": app_count 
            }
        }
    return {"status": "success", "found": False}

@router.post("/admin/update_seller")
def admin_update(data: AdminUpdateRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    
    if seller:
        seller.reference.update({
            "is_premium": data.seller_group == 2,
            "seller_group": data.seller_group,
            "coins": data.coins
        })
        return {"status": "success"}
    
    raise HTTPException(status_code=404, detail="Seller not found")

@router.post("/admin/publish_update")
def publish_update(data: AdminPublishUpdate):
    # Security check - ideally this would be in .env
    if data.secret_key != "lynx_admin_secret":
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
