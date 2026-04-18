import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

def migrate():
    # 1. Initialize Firebase (Use local key if available, else env)
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
    elif os.environ.get("SERVICE_ACCOUNT_JSON"):
        cred_dict = json.loads(os.environ.get("SERVICE_ACCOUNT_JSON"))
        cred = credentials.Certificate(cred_dict)
    else:
        print("❌ Error: No Firebase credentials found!")
        return

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    print("✅ Connected to Firebase.")

    # 2. Iterate through all sellers
    sellers = db.collection('sellers').stream()
    count = 0
    updated = 0

    print("🚀 Starting migration...")
    for seller in sellers:
        count += 1
        data = seller.to_dict()
        
        # If seller_group is missing, determine it from is_premium
        if 'seller_group' not in data:
            is_premium = data.get('is_premium', False)
            new_group = 2 if is_premium else 0
            
            # Update the document
            seller.reference.update({
                'seller_group': new_group
            })
            print(f"  - Migrated {data.get('email', 'unknown')}: {'Gold' if is_premium else 'Free'}")
            updated += 1
    
    print(f"\n✨ Migration complete!")
    print(f"   Total sellers scanned: {count}")
    print(f"   Total sellers updated: {updated}")

if __name__ == "__main__":
    migrate()
