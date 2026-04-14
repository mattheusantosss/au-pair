from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

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

if __name__ == "__main__":
    import uvicorn
    # Alterado para rodar na porta 8080 ou 8001
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)

