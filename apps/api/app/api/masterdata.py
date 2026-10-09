from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.api.schemas import CustomerIn, CustomerOut, SupplierIn, SupplierOut
from app.core.errors import not_found
from app.core.rbac import Perm
from app.db import get_db
from app.models.identity import Customer, Supplier, User
from app.services import audit

router = APIRouter(tags=["masterdata"])


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    return db.execute(select(Customer).where(Customer.tenant_id == user.tenant_id).order_by(Customer.name)).scalars().all()


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, user: User = Depends(require(Perm.MASTERDATA_MANAGE)), db: Session = Depends(get_db)):
    exists = db.execute(select(Customer).where(Customer.tenant_id == user.tenant_id, Customer.code == body.code)).scalar()
    if exists:
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE", "message": "customer code exists"})
    c = Customer(tenant_id=user.tenant_id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, tenant_id=user.tenant_id, actor=audit.Actor.user(user), action="customer.created", entity_type="customer",
                 entity_id=c.id, after=body.model_dump())
    db.commit()
    return c


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    return db.execute(select(Supplier).where(Supplier.tenant_id == user.tenant_id).order_by(Supplier.name)).scalars().all()


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, user: User = Depends(require(Perm.MASTERDATA_MANAGE)), db: Session = Depends(get_db)):
    if body.customer_id and not db.execute(
        select(Customer).where(Customer.id == body.customer_id, Customer.tenant_id == user.tenant_id)
    ).scalar():
        raise not_found("customer")
    s = Supplier(tenant_id=user.tenant_id, **body.model_dump())
    db.add(s)
    db.flush()
    audit.record(db, tenant_id=user.tenant_id, actor=audit.Actor.user(user), action="supplier.created", entity_type="supplier",
                 entity_id=s.id, after=body.model_dump())
    db.commit()
    return s


def tenant_customer(db: Session, user: User, customer_id) -> Customer:
    c = db.execute(select(Customer).where(Customer.id == customer_id, Customer.tenant_id == user.tenant_id)).scalar()
    if not c:
        raise not_found("customer")
    return c


def tenant_supplier(db: Session, user: User, supplier_id) -> Supplier:
    s = db.execute(select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == user.tenant_id)).scalar()
    if not s:
        raise not_found("supplier")
    return s


__all__ = ["router", "tenant_customer", "tenant_supplier", "current_user"]
