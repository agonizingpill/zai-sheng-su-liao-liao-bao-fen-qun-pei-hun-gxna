from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import Session
from .security import current,allow
from .rework_models import ReworkOrder
from .rework_schemas import ReworkIn
from .blending import audit
from . import rework_service as svc
router=APIRouter()
@router.get('/rework-orders')
def orders(u=Depends(current)):
    with Session() as s:
        return [svc.rework_view(s,x) for x in s.scalars(select(ReworkOrder).order_by(ReworkOrder.id.desc()))]
@router.post('/rework-orders')
def split(p:ReworkIn,u=Depends(current)):
    allow(u,'admin','blender')
    # Source deduction and new-bale creation share one transaction; on failure nothing
    # is committed, and retrying the same order returns the existing event, never a double split.
    with Session.begin() as s:return svc.create_rework(s,p,u)
@router.get('/pellet-checks/{id}/rework')
def detail(id:int,u=Depends(current)):
    from .quality_models import PelletCheck
    from .blending import get
    with Session() as s:return svc.check_detail(s,get(s,PelletCheck,id))
@router.get('/bales/{id}/lineage')
def lineage(id:int,u=Depends(current)):
    from .models import Bale
    from .blending import get
    with Session() as s:
        b=get(s,Bale,id)
        data=svc.bale_lineage(s,b)
        return {'bale_id':b.id,'bale_code':b.code,'is_rework':data is not None,'lineage':data}
