from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Expense, User
from app.schemas import ExpenseCreate, ExpenseOut

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    limit: int = 100,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[Expense]:
    return (
        db.query(Expense)
        .filter(Expense.user_id == current.id)
        .order_by(Expense.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> Expense:
    exp = Expense(
        user_id=current.id,
        amount_inr=data.amount_inr,
        category=data.category,
        note=data.note,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp
