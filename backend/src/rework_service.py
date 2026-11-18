"""Rework of quarantined pellets.

A quarantined PelletCheck can divert part of its weight into a brand new bale. The
split, the source deduction and the new bale are written in one transaction: either
all of it happens or none of it. Certified checks are immutable and refuse rework,
while rework and certify/retest serialize on the PelletCheck row so one lot can only
take one direction at a time.
"""
from decimal import Decimal
from datetime import datetime,timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from .models import Bale,Blend,BlendPortion
from .quality_models import PelletCheck
from .rework_models import ReworkOrder
from .blending import obj,get,audit
from .constants import REWORK_BALE_PREFIX,REWORK_ORDER_PREFIX

def _utc():return datetime.now(timezone.utc).isoformat()
def total_reworked_kg(s,check_id,lock=False):
    q=select(ReworkOrder).where(ReworkOrder.source_check_id==check_id)
    if lock:q=q.with_for_update().execution_options(populate_existing=True)
    return sum((x.kg for x in s.scalars(q)),Decimal(0))
def certifiable_kg(s,check,lock=False):
    """Saleable output = measured output minus every kg already diverted to rework.

    Diverted weight is never counted again as certifiable/saleable production."""
    return check.actual_kg-total_reworked_kg(s,check.id,lock)
def _rework_bale_ids(s,check):
    ids=[p.bale_id for p in s.scalars(select(BlendPortion).where(BlendPortion.blend_id==check.blend_id))]
    if not ids:return set()
    return set(s.scalars(select(ReworkOrder.new_bale_id).where(ReworkOrder.new_bale_id.in_(ids))))
def parent_orders(s,check):
    """Rework events whose output bale fed the blend behind this check (its parents)."""
    ids=_rework_bale_ids(s,check)
    if not ids:return []
    return list(s.scalars(select(ReworkOrder).where(ReworkOrder.new_bale_id.in_(ids)).order_by(ReworkOrder.id)))
def _lineage(parents):
    seen,chain=set(),[]
    for p in parents:
        for node in (p.lineage or []):
            if node['order_id'] not in seen:
                seen.add(node['order_id']);chain.append(node)
    return chain
def create_rework(s,data,u):
    check=get(s,PelletCheck,data.check_id,True)  # row lock: serializes vs certify/retest
    kg=data.kg
    # Idempotent retry: the same lot+weight+reason (or an explicit token) returns the
    # existing order instead of deducting again or building a second bale.
    token=(data.request_token or '').strip() or None
    # Locking read: under MySQL REPEATABLE READ a FOR UPDATE sees the latest committed
    # rework events, so a concurrent committed split is never missed in the balance check.
    existing=s.scalars(select(ReworkOrder).where(ReworkOrder.source_check_id==check.id).order_by(ReworkOrder.id).with_for_update().execution_options(populate_existing=True)).all()
    for o in existing:
        same_token=token is not None and (o.source_snapshot or {}).get('request_token')==token
        if same_token or (o.kg==kg and o.reason==data.reason.strip() and token is None):
            return rework_view(s,o)
    if check.state=='certified':
        raise HTTPException(409,'该粒料已签发合格证，签证记录冻结，拒绝返工')
    if check.state!='quarantine':
        raise HTTPException(409,'只有PVC越限的隔离粒料可拆出返工，合格粒料请走复检发证')
    already=sum((o.kg for o in existing),Decimal(0))
    available=check.actual_kg-already
    if kg>available:
        raise HTTPException(409,f'返工{kg}kg超过该料剩余可拆重量{available}kg（已返工{already}kg），未扣源料也未建新包')
    parents=parent_orders(s,check)
    generation=(max((p.generation for p in parents),default=0)+1)
    root=min((p.root_check_id for p in parents),default=check.id)
    chain=_lineage(parents)
    blend=s.get(Blend,check.blend_id)
    # Freeze the original inspection, measurement history and 投料 snapshot.
    source_snapshot={
        'check_id':check.id,'blend_id':check.blend_id,'blend_code':blend.code,
        'actual_kg':float(check.actual_kg),'melt_index':float(check.melt_index),
        'pvc_ppm':float(check.pvc_ppm),'state':check.state,
        'inspections':check.inspections,'input_snapshot':check.input_snapshot,
        'request_token':token,'diverted_at':_utc(),
    }
    # Moisture is not re-measured on pellets; carry the weighted moisture of the 投料 snapshot.
    portions=(check.input_snapshot or {}).get('portions',[])
    total_w=sum((Decimal(str(p['kg']))for p in portions),Decimal(0)) or Decimal(1)
    moisture=(sum((Decimal(str(p['kg']))*Decimal(str(p['moisture_snapshot']))for p in portions),Decimal(0))/total_w).quantize(Decimal('.001'))
    # Use a unique temporary code so concurrent splits on different checks can never
    # collide on the unique bale code before the id is known; replace it once flushed.
    tmp=uuid4().hex[:12]
    bale=Bale(
        code=f'{REWORK_BALE_PREFIX}-G{generation}-TMP-{tmp}',kg=kg,available_kg=kg,
        melt_index=check.melt_index,moisture=moisture,pvc_ppm=check.pvc_ppm,
        cluster_id=None,cluster_version=None,
    )
    s.add(bale);s.flush()
    bale.code=f'{REWORK_BALE_PREFIX}-G{generation}-{bale.id:05d}'
    order=ReworkOrder(
        code=f'{REWORK_ORDER_PREFIX}-TMP-{tmp}',source_check_id=check.id,new_bale_id=bale.id,
        kg=kg,reason=data.reason.strip(),generation=generation,root_check_id=root,
        lineage=[],source_snapshot=source_snapshot,created_by=u['email'],
    )
    s.add(order);s.flush()
    order.code=f'{REWORK_ORDER_PREFIX}-{order.id:06d}'
    order.lineage=chain+[{
        'order_id':order.id,'order_code':order.code,'bale_id':bale.id,'bale_code':bale.code,
        'check_id':check.id,'kg':float(kg),'generation':generation,'root_check_id':root,
        'reason':order.reason,'created_by':u['email'],'at':_utc(),
    }]
    s.flush()
    audit(s,u,'pellet_reworked',f'{order.code} / {blend.code} / {kg}kg / G{generation}')
    return rework_view(s,order)
def rework_view(s,o):
    check=s.get(PelletCheck,o.source_check_id);bale=s.get(Bale,o.new_bale_id)
    blend=s.get(Blend,check.blend_id)
    return {**obj(o),'blend_code':blend.code,'new_bale_code':bale.code,
            'source_actual_kg':float(check.actual_kg),'check_state':check.state,
            'lineage_depth':len(o.lineage)}
def check_detail(s,check):
    """Per-lot reconciliation: waiting-to-rework, already-reworked and certifiable kg."""
    reworked=total_reworked_kg(s,check.id)
    blend=s.get(Blend,check.blend_id)
    events=[rework_view(s,o) for o in s.scalars(select(ReworkOrder).where(ReworkOrder.source_check_id==check.id).order_by(ReworkOrder.id))]
    return {
        'check_id':check.id,'blend_code':blend.code,'check_state':check.state,
        'actual_kg':float(check.actual_kg),'reworked_kg':float(reworked),
        'certifiable_kg':float((check.actual_kg-reworked).quantize(Decimal('.001'))),
        'events':events,
    }
def bale_lineage(s,bale):
    o=s.scalar(select(ReworkOrder).where(ReworkOrder.new_bale_id==bale.id))
    if not o:return None
    return {'rework_order_id':o.id,'rework_order_code':o.code,'generation':o.generation,
            'root_check_id':o.root_check_id,'lineage':o.lineage,'source_check_id':o.source_check_id}
