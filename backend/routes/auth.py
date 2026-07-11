import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from firebase_admin import firestore
from database import db
from schemas import SellerSyncRequest, SellerDeleteRequest, SellerRedeemCodeRequest

router = APIRouter(tags=["Auth"])

@router.post("/auth/sync")
def sync_seller(data: SellerSyncRequest):
    doc_ref = db.collection('sellers').document(data.firebase_uid)
    doc = doc_ref.get()
    
    if doc.exists:
        d = doc.to_dict()
        existing_id = d.get('ownerid')
        
        if not existing_id:
            existing_id = str(uuid.uuid4())
            doc_ref.update({'ownerid': existing_id})

        group = d.get('seller_group', 0)
        plan_expires_at = d.get('plan_expires_at')
        if plan_expires_at:
            try:
                expiry_date = datetime.fromisoformat(plan_expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expiry_date:
                    doc_ref.update({'seller_group': 0, 'plan_expires_at': None})
                    group = 0
            except Exception:
                pass

        if 'seller_group' not in d:
             doc_ref.update({'seller_group': 0})
            
        return {
            "status": "success", 
            "ownerid": existing_id, 
            "coins": d.get('coins', 0), 
            "seller_group": group,
            "plan_expires_at": d.get('plan_expires_at')
        }
    else:
        new_ownerid = str(uuid.uuid4())
        doc_ref.set({
            'email': data.email,
            'ownerid': new_ownerid,
            'coins': 400,
            'seller_group': 0,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        return {"status": "success", "ownerid": new_ownerid, "coins": 400, "seller_group": 0}

@router.post("/seller/redeem_code")
def redeem_code(data: SellerRedeemCodeRequest):
    codes = db.collection('gift_codes').where('code', '==', data.code).limit(1).get()
    if not codes:
        raise HTTPException(status_code=400, detail="Invalid gift code")
    code_doc = codes[0]
    code_data = code_doc.to_dict()
    if code_data.get('disabled', False):
        raise HTTPException(status_code=400, detail="This gift code has been disabled")
    max_uses = code_data.get('max_uses', 1)
    use_count = code_data.get('use_count', 0)
    if max_uses != 0 and use_count >= max_uses:
        raise HTTPException(status_code=400, detail="This gift code has reached its usage limit")

    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).get()
    if not seller_query:
        raise HTTPException(status_code=404, detail="Seller not found")
    seller_doc = seller_query[0]
    seller_data = seller_doc.to_dict()

    days = code_data.get("duration_days", 30)
    new_expiry = datetime.now(timezone.utc) + timedelta(days=days)

    current_group = seller_data.get('seller_group', 0)
    current_expiry_str = seller_data.get('plan_expires_at')
    if current_group == code_data['tier'] and current_expiry_str:
        try:
            current_expiry = datetime.fromisoformat(current_expiry_str.replace("Z", "+00:00"))
            if current_expiry > datetime.now(timezone.utc):
                new_expiry = current_expiry + timedelta(days=days)
        except Exception:
            pass

    seller_doc.reference.update({
        'seller_group': code_data['tier'],
        'plan_expires_at': new_expiry.isoformat()
    })

    new_use_count = use_count + 1
    exhausted = max_uses != 0 and new_use_count >= max_uses
    code_doc.reference.update({
        'use_count': new_use_count,
        'used': exhausted,
        'used_by': data.ownerid,
        'used_at': datetime.now(timezone.utc).isoformat()
    })

    return {"status": "success", "tier": code_data['tier'], "expires_at": new_expiry.isoformat()}

@router.post("/seller/delete")
def delete_seller(data: SellerDeleteRequest):
    seller_query = db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).get()
    if not seller_query:
        return {"status": "error", "message": "Seller not found"}
    
    seller_query[0].reference.delete()

    apps = db.collection('applications').where('ownerid', '==', data.ownerid).stream()
    for a in apps:
        appid = a.get('appid')
        users = db.collection('users').where('appid', '==', appid).stream()
        for u in users: 
            u.reference.delete()
        licenses = db.collection('licenses').where('appid', '==', appid).stream()
        for l in licenses: 
            l.reference.delete()
        a.reference.delete()
    return {"status": "success"}

