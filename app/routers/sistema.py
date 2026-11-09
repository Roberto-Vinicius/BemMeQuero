from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ADMIN, TODOS, get_db, require_role
from app.core.exceptions import RegraDeNegocioError
from app.core.security import hash_senha, verificar_senha
from app.core.templates import templates
from app.models import ConfiguracaoSistema, Usuario
from app.services import produto_service

router = APIRouter(prefix="/sistema", tags=["sistema"])


def _obter_config(db: Session) -> ConfiguracaoSistema:
    cfg = db.scalar(select(ConfiguracaoSistema).limit(1))
    if not cfg:
        cfg = ConfiguracaoSistema(
            nome_empresa="Bem Me Quero Perfumaria",
            fuso_horario="America/Fortaleza",
            formato_data="DD/MM/AAAA",
            moeda_padrao="BRL",
            nivel_minimo_padrao=5,
            antecedencia_vencimento_dias=30,
            notificar_estoque_baixo=True,
            permitir_estoque_negativo=False,
            ativar_lotes=True,
            emails_notificacao="admin@bemmequero.local, estoque@bemmequero.local",
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("")
def index(
    request: Request,
    salvo: str = "",
    erro: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*TODOS)),
):
    cfg = _obter_config(db)
    emails = [e.strip() for e in (cfg.emails_notificacao or "").split(",") if e.strip()]
    return templates.TemplateResponse(
        request,
        "sistema/index.html",
        {
            "usuario": usuario,
            "cfg": cfg,
            "emails": emails,
            "salvo": salvo,
            "erro": erro,
        },
    )


@router.post("/configuracoes")
def salvar_configuracoes(
    nome_empresa: str = Form("Bem Me Quero Perfumaria"),
    fuso_horario: str = Form("America/Fortaleza"),
    formato_data: str = Form("DD/MM/AAAA"),
    moeda_padrao: str = Form("BRL"),
    idioma: str = Form("pt-BR"),
    limite_estoque_baixo_padrao: int = Form(5),
    dias_alerta_validade: int = Form(30),
    notificar_estoque_baixo: str = Form(""),
    bloquear_saida_sem_estoque: str = Form(""),
    sugerir_fefo_automatico: str = Form(""),
    emails_notificacao: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*ADMIN)),
):
    cfg = _obter_config(db)
    cfg.nome_empresa = nome_empresa.strip() or "Bem Me Quero Perfumaria"
    cfg.fuso_horario = fuso_horario
    cfg.formato_data = formato_data
    cfg.moeda_padrao = moeda_padrao
    cfg.nivel_minimo_padrao = max(0, limite_estoque_baixo_padrao)
    cfg.antecedencia_vencimento_dias = max(1, dias_alerta_validade)
    cfg.notificar_estoque_baixo = notificar_estoque_baixo == "on"
    cfg.permitir_estoque_negativo = bloquear_saida_sem_estoque != "on"
    cfg.ativar_lotes = sugerir_fefo_automatico == "on"
    cfg.emails_notificacao = emails_notificacao.strip()
    db.commit()
    return RedirectResponse("/sistema?salvo=config", status_code=303)


@router.post("/perfil")
async def salvar_perfil(
    request: Request,
    nome: str = Form(...),
    sobrenome: str = Form(""),
    telefone: str = Form(""),
    cargo: str = Form(""),
    senha_atual: str = Form(""),
    nova_senha: str = Form(""),
    confirmar_senha: str = Form(""),
    avatar: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*TODOS)),
):
    u = db.get(Usuario, usuario.id)
    u.nome = nome.strip() or u.nome
    u.sobrenome = sobrenome.strip() or None
    u.telefone = telefone.strip() or None
    u.cargo = cargo.strip() or None

    if avatar and avatar.filename:
        try:
            u.avatar_path = produto_service.salvar_foto(avatar.filename, await avatar.read())
        except RegraDeNegocioError as e:
            return RedirectResponse(f"/sistema?erro={e.mensagem}", status_code=303)

    if nova_senha.strip():
        if not verificar_senha(senha_atual, u.senha_hash):
            return RedirectResponse("/sistema?erro=Senha+atual+incorreta.", status_code=303)
        if len(nova_senha) < 8:
            return RedirectResponse("/sistema?erro=A+nova+senha+deve+ter+ao+menos+8+caracteres.", status_code=303)
        if nova_senha != confirmar_senha:
            return RedirectResponse("/sistema?erro=A+confirmação+da+nova+senha+não+confere.", status_code=303)
        u.senha_hash = hash_senha(nova_senha)

    db.commit()
    return RedirectResponse("/sistema?salvo=perfil", status_code=303)


@router.get("/backup")
def fazer_backup_agora(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*ADMIN)),
):
    cfg = _obter_config(db)
    cfg.ultimo_backup_em = datetime.now(timezone.utc)
    db.commit()
    db_path = Path(__file__).resolve().parent.parent.parent / "bemmequero.db"
    hoje = datetime.now().strftime("%Y%m%d_%H%M")
    return FileResponse(
        path=db_path,
        media_type="application/octet-stream",
        filename=f"bemmequero_backup_{hoje}.db",
    )
