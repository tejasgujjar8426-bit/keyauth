from pydantic import BaseModel

class SellerSyncRequest(BaseModel): firebase_uid: str; email: str
class SellerDeleteRequest(BaseModel): ownerid: str
class AppCreateRequest(BaseModel): ownerid: str; app_name: str
class AppDeleteRequest(BaseModel): appid: str
class EndUserCreateRequest(BaseModel): ownerid: str; appid: str; username: str; password: str; days: int; expire_str: str = None
class ApiLoginRequest(BaseModel): ownerid: str; app_secret: str; username: str; password: str; hwid: str
class UserListRequest(BaseModel): appid: str
class UserDeleteRequest(BaseModel): user_id: str
class UserExtendRequest(BaseModel): user_id: str; days: int

class WebhookSaveRequest(BaseModel): 
    appid: str
    webhook_url: str
    enabled: bool
    show_hwid: bool
    show_app: bool
    show_expiry: bool

class AdminSearchRequest(BaseModel): ownerid: str
class AdminUpdateRequest(BaseModel): ownerid: str; coins: int; seller_group: int = 0

class AdminPublishUpdate(BaseModel):
    message: str
    secret_key: str

class UserUpdateAction(BaseModel):
    user_id: str
    action: str 
    expire_str: str = None 
    lock_state: bool = False

class LicenseCreateRequest(BaseModel):
    ownerid: str
    appid: str
    license_key: str
    days: int
    expire_str: str = None

class LicenseListRequest(BaseModel):
    appid: str

class LicenseDeleteRequest(BaseModel):
    license_id: str

class LicenseActionRequest(BaseModel):
    license_id: str
    action: str
    expire_str: str = None
    lock_state: bool = False

class ApiLicenseLoginRequest(BaseModel):
    ownerid: str
    app_secret: str
    license_key: str
    hwid: str
