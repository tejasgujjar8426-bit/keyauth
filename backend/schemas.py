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
class AdminUpdateRequest(BaseModel): ownerid: str; seller_group: int = 0

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

class AdminVerifyRequest(BaseModel):
    secret_key: str

class AdminSellersRequest(BaseModel):
    secret_key: str

class AdminUsersRequest(BaseModel):
    secret_key: str

class AdminCodesRequest(BaseModel):
    secret_key: str

class AdminCodeGenerateRequest(BaseModel):
    secret_key: str
    tier: int
    duration_days: int
    max_uses: int = 1

class AdminCleanRequest(BaseModel):
    secret_key: str

class SellerRedeemCodeRequest(BaseModel):
    ownerid: str
    code: str

class AdminCodeActionRequest(BaseModel):
    secret_key: str
    code_id: str
    action: str


