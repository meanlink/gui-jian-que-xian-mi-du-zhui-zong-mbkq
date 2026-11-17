from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from src.config.database import get_db
from src.models import ClosureOrder, AcceptancePeriod, Retest
from src.schemas.closure import ClosureOrderInput, RetestInput, ReworkInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import closure as closure_service
from src.services.audit import record
from src.utils.serialization import closure_order_dict, period_dict, retest_dict

router = APIRouter(prefix='/closure')


@router.get('/bands')
def bands(job_id: int, db=Depends(get_db), u=Depends(current_user)):
    return closure_service.list_bands(db, job_id)


@router.get('/orders')
def orders(db=Depends(get_db), u=Depends(current_user)):
    rows = db.scalars(select(ClosureOrder).order_by(ClosureOrder.id.desc()).limit(200))
    return [closure_order_dict(o) for o in rows]


@router.post('/orders', status_code=201)
def create_order(data: ClosureOrderInput, db=Depends(get_db), u=Depends(can_write)):
    order, period = closure_service.create_order(db, data, u)
    record(db, u.email, 'closure.order_create',
           {'id': order.id, 'job_id': order.job_id, 'band': order.band_key,
            'range': [order.from_km, order.to_km], 'completed_at': order.completed_at})
    db.commit()
    return closure_order_dict(order)


@router.get('/orders/{id}')
def order_detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    order, periods, retests = closure_service.order_detail(db, id)
    return {
        'order': closure_order_dict(order),
        'periods': [period_dict(p) for p in periods],
        'retests': [retest_dict(r) for r in retests],
    }


@router.post('/retests', status_code=201)
def register_retest(data: RetestInput, db=Depends(get_db), u=Depends(can_write)):
    order, period, retest, duplicated = closure_service.register_retest(db, data, u)
    record(db, u.email, 'closure.retest_duplicate' if duplicated else 'closure.retest_register',
           {'id': retest.id, 'order_id': order.id, 'period': period.period_no,
            'result': retest.result, 'duplicated': duplicated,
            'order_status': order.status})
    db.commit()
    return {'retest': retest_dict(retest), 'order': closure_order_dict(order),
            'duplicated': duplicated}


@router.post('/orders/{id}/rework', status_code=201)
def rework(id: int, data: ReworkInput, db=Depends(get_db), u=Depends(admin_only)):
    order, period = closure_service.rework(db, id, u, data.reason)
    record(db, u.email, 'closure.rework',
           {'id': order.id, 'new_period': period.period_no, 'reason': period.reason})
    db.commit()
    return {'order': closure_order_dict(order), 'period': period_dict(period)}


@router.get('/stats')
def stats(db=Depends(get_db), u=Depends(current_user)):
    total = db.scalar(select(func.count()).select_from(ClosureOrder))
    closed = db.scalar(select(func.count()).select_from(ClosureOrder).where(ClosureOrder.status == 'closed'))
    retest_count = db.scalar(select(func.count()).select_from(Retest))
    return {'orders': total or 0, 'closed': closed or 0,
            'open': (total or 0) - (closed or 0), 'retests': retest_count or 0}
