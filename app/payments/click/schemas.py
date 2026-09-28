from pydantic import BaseModel, ConfigDict


class PrepareFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    click_trans_id: str
    service_id: str
    click_user_id: str | None = None
    merchant_trans_id: str
    amount: str
    action: str
    sign_time: str
    sign_string: str


class CompleteFields(PrepareFields):
    merchant_prepare_id: str
    error: str
    error_note: str
    click_paydoc_id: str


class PrepareResponse(BaseModel):
    click_trans_id: int
    merchant_trans_id: str
    merchant_prepare_id: int
    error: int
    error_note: str


class CompleteResponse(BaseModel):
    click_trans_id: int
    merchant_trans_id: str
    merchant_confirm_id: int
    error: int
    error_note: str
