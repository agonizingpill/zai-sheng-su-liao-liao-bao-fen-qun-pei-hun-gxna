from decimal import Decimal
from pydantic import BaseModel,Field
class ReworkIn(BaseModel):
    # PelletCheck id whose quarantined material is being diverted.
    check_id:int=Field(gt=0)
    kg:Decimal=Field(gt=0,le=100000,max_digits=12,decimal_places=3)
    reason:str=Field(min_length=8,max_length=600)
    # Optional client-supplied idempotency token for safe retry of the same request.
    request_token:str|None=Field(default=None,max_length=80)
