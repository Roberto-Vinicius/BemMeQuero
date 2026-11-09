from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import TODOS, get_db, require_role
from app.core.templates import templates
from app.models import Usuario
from app.services import dashboard_service

router = APIRouter(tags=["painel"])


@router.get("/")
def painel(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*TODOS))):
    return templates.TemplateResponse(request, "dashboard.html", {
        "usuario": usuario, "p": dashboard_service.montar_painel(db),
    })

