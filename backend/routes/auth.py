import uuid
from fastapi import APIRouter
from firebase_admin import firestore
from database import db
from schemas import SellerSyncRequest, SellerDeleteRequest

router = APIRouter(tags=["Auth"])

@router.post("/auth/sync")
def sync_seller(data: SellerSyncRequest):
    doc_ref = db.collection('sellers').document(data.firebase_uid)
    doc = doc_ref.get()
    
    if doc.exists:
        d = doc.to_dict()
        existing_id = d.get('ownerid')
        return {
            "status": "success", 
            "ownerid": existing_id, 
            "coins": d.get('coins', 0), 
            "is_premium": d.get('is_premium', False)
        }
    else:
        new_ownerid = str(uuid.uuid4())
        doc_ref.set({
            'email': data.email,
            'ownerid': new_ownerid,
            'coins': 400,
            'is_premium': False,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        return {"status": "success", "ownerid": new_ownerid, "coins": 400, "is_premium": False}

@router.post("/seller/delete")
def delete_seller(data: SellerDeleteRequest):
    db.collection('sellers').where('ownerid', '==', data.ownerid).limit(1).get()[0].reference.delete()
    apps = db.collection('applications').where('ownerid', '==', data.ownerid).stream()
    for a in apps:
        users = db.collection('users').where('appid', '==', a.get('appid')).stream()
        for u in users: u.reference.delete()
        a.reference.delete()
    return {"status": "success"}
