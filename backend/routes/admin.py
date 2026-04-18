from fastapi import APIRouter, HTTPException
from database import db
from schemas import AdminSearchRequest, AdminUpdateRequest

router = APIRouter(tags=["Admin"])

@router.post("/admin/stats")
def get_admin_stats():
    # Count Total Sellers
    sellers_agg = db.collection('sellers').count()
    sellers_count = sellers_agg.get()[0][0].value

    # Count Total End Users
    users_agg = db.collection('users').count()
    users_count = users_agg.get()[0][0].value

    # Count Premium Sellers
    prem_agg = db.collection('sellers').where('is_premium', '==', True).count()
    prem_count = prem_agg.get()[0][0].value

    # --- NEW: Count Total Apps ---
    apps_agg = db.collection('applications').count()
    apps_count = apps_agg.get()[0][0].value

    return {
        "status": "success",
        "sellers": sellers_count,
        "users": users_count,
        "premium": prem_count,
        "apps": apps_count  # <--- Added this to response
    }

@router.post("/admin/search_seller")
def admin_search(data: AdminSearchRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).stream()
    seller = next(seller_query, None)
    
    if seller:
        d = seller.to_dict()
        
        # Count Apps for this specific seller
        app_agg = db.collection('applications').where('ownerid', '==', data.ownerid).count()
        app_count = app_agg.get()[0][0].value

        return {
            "status": "success",
            "found": True,
            "data": {
                "email": d.get('email'),
                "ownerid": d.get('ownerid'),
                "coins": d.get('coins', 0),
                "is_premium": d.get('is_premium', False),
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
            "is_premium": data.is_premium,
            "coins": data.coins
        })
        return {"status": "success"}
    
    raise HTTPException(status_code=404, detail="Seller not found")
