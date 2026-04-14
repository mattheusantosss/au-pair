import os
import json
import logging
import re
import httpx
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Configuração do ActiveCampaign
ACTIVE_CAMPAIGN_URL = os.getenv("ACTIVE_CAMPAIGN_URL")
ACTIVE_CAMPAIGN_API_KEY = os.getenv("ACTIVE_CAMPAIGN_API_KEY")
# Usando a Lista 4: "[Grupão AuPair] Lista de Leads Geral" com base na investigação
ACTIVE_CAMPAIGN_LIST_ID = 4

# -- Logs OBRIGATÓRIOS conf --
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("css_hub_integration")

from database import engine, Base, get_db

# Cria as tabelas no banco SQLite ao iniciar a aplicação
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AuPair")

# Montando a estrutura Flask-like
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def index(request: Request, db: Session = Depends(get_db)):
    # Aqui os dados podem ser manipulados usando Jinja2. Ex de uso do banco 'db'.
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={"message": "Bem-vindo ao Ambiente Virtual FastAPI + SQLite!"}
    )

class LeadInput(BaseModel):
    nome: str
    email: str
    whatsapp: str
    status: str
    css_token: str | None = None

@app.post("/api/lead")
async def submit_lead(lead: LeadInput, db: Session = Depends(get_db)):
    # 4) PREPARAÇÃO DE DADOS REST (Tratamento)
    telefone_limpo = re.sub(r'\D', '', lead.whatsapp)
    
    # --- INTEGRAÇÃO ACTIVE CAMPAIGN ---
    if ACTIVE_CAMPAIGN_URL and ACTIVE_CAMPAIGN_API_KEY:
        ac_url_sync = f"{ACTIVE_CAMPAIGN_URL}/api/3/contact/sync"
        ac_headers = {
            "Api-Token": ACTIVE_CAMPAIGN_API_KEY,
            "Content-Type": "application/json"
        }
        nome_partes = lead.nome.split(" ", 1)
        first_name = nome_partes[0]
        last_name = nome_partes[1] if len(nome_partes) > 1 else ""
        
        ac_payload = {
            "contact": {
                "email": lead.email,
                "firstName": first_name,
                "lastName": last_name,
                "phone": lead.whatsapp,  # Pode enviar limpo ou formatado
                "fieldValues": [
                    {
                        "field": "2",  # Campo customizado de Status
                        "value": lead.status
                    }
                ]
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                logger.info("Enviando Lead %s para ActiveCampaign (Sync)...", lead.email)
                ac_response = await client.post(ac_url_sync, json=ac_payload, headers=ac_headers)
                if ac_response.status_code in (200, 201):
                    ac_data = ac_response.json()
                    contact_id = ac_data.get("contact", {}).get("id")
                    if contact_id:
                        # Adicionar contato à lista
                        ac_list_payload = {
                            "contactList": {
                                "list": ACTIVE_CAMPAIGN_LIST_ID,
                                "contact": contact_id,
                                "status": 1 # 1 = Active
                            }
                        }
                        await client.post(f"{ACTIVE_CAMPAIGN_URL}/api/3/contactLists", json=ac_list_payload, headers=ac_headers)
                        logger.info("Contato ActiveCampaign (ID: %s) adicionado à lista %s com sucesso.", contact_id, ACTIVE_CAMPAIGN_LIST_ID)
                else:
                    logger.error("Erro ActiveCampaign Sync: %s", ac_response.text)
            except Exception as e:
                logger.error("Exceção ao integrar com ActiveCampaign: %s", str(e))
    # --- FIM INTEGRAÇÃO ACTIVE CAMPAIGN ---

    # 6) VERIFICAÇÃO DO KAizen CSS (Tracking)
    if not lead.css_token or not lead.css_token.strip():
        logger.warning("Token CSS ausente para o lead %s. Fluxo interno seguido sem integração com o Tracking CSS.", lead.email)
        return {"status": "success", "message": "Lead salvo e enviado ao Active Campaign - Sem Cookie de Rastreio CSS."}
    
    # 7) LOGS Kaizen: Rastros Auditáveis de depuração
    masked_token = lead.css_token[:10] + "***" if len(lead.css_token) > 10 else "***"
    logger.info("CSS token detectado para %s: %s", lead.email, masked_token)
    
    # Serializando os Meta-fields customizados p/ a estrutura de Array
    data_fields = [
        {"key": "status", "title": "Status do Lead", "value": lead.status, "searchable": True}
    ]
    
    url = "https://css.agenciakaizen.com.br/api/register/lead"
    payload = {
        "token": lead.css_token,
        "customer_domain": "lp.aupairgrupao.com.br",
        "captation_means": "form_landing_page",
        "name": lead.nome,
        "email": lead.email,
        "phone_countrycode": "55",
        "phone": telefone_limpo,
        "message": f"Novo cadastro AuPair: {lead.status}",
        "message_complete": f"Nome: {lead.nome}\nEmail: {lead.email}\nStatus: {lead.status}",
        "send": json.dumps({"type": "email"}),
        "data": json.dumps(data_fields)
    }
    
    # Motor Assíncrono do HTTPX p/ o POST externo Kaizen
    async with httpx.AsyncClient() as client:
        try:
            logger.info("Emitindo POST Application/URL-Encoded para -> Kaizen CSS API")
            response = await client.post(
                url, 
                data=payload, 
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            logger.info("Status Code do CSS Hub retornado: %s", response.status_code)
            
            if response.status_code not in (200, 201):
                logger.error("Falha ao registrar lado CSS. Resposta CSS parcial: %s", response.text[:200])
        except Exception as e:
            logger.error("Exceção crassa de conexão ao contatar CSS Hub Backend API: %s", str(e))
            
    return {"status": "success", "message": "Lead salvo com rastreamento (ActiveCampaign + Kaizen)"}

if __name__ == "__main__":
    import uvicorn
    # Alterado para rodar na porta 8080 ou 8001
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)

