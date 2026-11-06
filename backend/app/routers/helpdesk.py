from typing import Annotated

from fastapi import APIRouter, Depends

from ..auth import require_role
from ..models import User

router = APIRouter(prefix="/helpdesk", tags=["helpdesk"])


@router.get("/queue")
def helpdesk_queue(user: Annotated[User, Depends(require_role("helpdesk"))]):
    return {"items": []}
