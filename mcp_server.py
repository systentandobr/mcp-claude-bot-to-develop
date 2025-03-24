import asyncio
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

import anthropic
import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from git import Repo
from langchain.chains import LLMChain
from langchain.chat_models import ChatAnthropic
from langchain.prompts import PromptTemplate
from pydantic import BaseModel

# Carrega variáveis de ambiente
load_dotenv()

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuração das chaves de API
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPOS_BASE_PATH = os.getenv(
    "REPOS_BASE_PATH"
)  # Diretório raiz onde estão todos os repositórios
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Inicializa o cliente Claude
claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# Armazenamento do repositório atual de cada usuário
user_current_repos = {}

# Inicializa a aplicação FastAPI
app = FastAPI(title="MCP Server - Gerenciador de Repositório com IA")


# Modelos de dados
class RepoSelectionRequest(BaseModel):
    repo_name: str
    chat_id: str


class FileModificationRequest(BaseModel):
    file_path: str
    description: str
    chat_id: str
    repo_name: str = (
        None  # Opcional, usa o repositório atualmente selecionado se não especificado
    )


class ApplyModificationRequest(BaseModel):
    suggestion_id: str
    chat_id: str


class CommitRequest(BaseModel):
    message: str
    chat_id: str
    repo_name: str = (
        None  # Opcional, usa o repositório atualmente selecionado se não especificado
    )


class PushRequest(BaseModel):
    chat_id: str
    repo_name: str = (
        None  # Opcional, usa o repositório atualmente selecionado se não especificado
    )


class NavigationRequest(BaseModel):
    path: str = ""
    chat_id: str
    repo_name: str = (
        None  # Opcional, usa o repositório atualmente selecionado se não especificado
    )


# Armazenamento de sugestões
suggestions_store = {}


# Funções auxiliares
def send_telegram_message(chat_id: str, text: str):
    """Envia mensagem para o usuário via Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para o Telegram: {str(e)}")
        return None


def get_repo_for_user(chat_id: str, repo_name: str = None):
    """Obtém o repositório atual do usuário."""
    if chat_id not in user_current_repos:
        return (
            None,
            "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um.",
        )

    if repo_name:
        # Busca o repositório especificado
        repo_path = os.path.join(REPOS_BASE_PATH, repo_name)
        if not os.path.isdir(repo_path) or not os.path.isdir(
            os.path.join(repo_path, ".git")
        ):
            return (
                None,
                f"Repositório '{repo_name}' não encontrado ou não é um repositório Git válido.",
            )

        return Repo(repo_path), None
    else:
        # Usa o repositório atualmente selecionado
        repo_info = user_current_repos[chat_id]
        return Repo(repo_info["repo_path"]), None


async def update_repository(repo_instance):
    """Atualiza o repositório local com as alterações remotas."""
    try:
        origin = repo_instance.remotes.origin
        origin.pull()
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar repositório: {str(e)}")
        return False


def run_github_action(workflow_name: str):
    """Executa uma GitHub Action específica."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Extrai o proprietário e o nome do repositório da URL
    repo_parts = REPO_URL.split("/")
    owner = repo_parts[-2]
    repo_name = repo_parts[-1].replace(".git", "")

    url = f"https://api.github.com/repos/{owner}/{repo_name}/actions/workflows/{workflow_name}/dispatches"

    payload = {"ref": "main"}  # Ou a branch que você está usando

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 204:
            return True
        else:
            logger.error(f"Erro ao executar GitHub Action: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Erro ao executar GitHub Action: {str(e)}")
        return False


# Rotas da API
@app.get("/")
async def root():
    return {"message": "MCP Server - Gerenciador de Repositório com IA"}


@app.get("/repos")
async def list_repos(chat_id: str):
    """Lista todos os repositórios disponíveis."""
    try:
        # Lista todos os diretórios no caminho base que são repositórios Git
        repos = [
            d
            for d in os.listdir(REPOS_BASE_PATH)
            if os.path.isdir(os.path.join(REPOS_BASE_PATH, d))
            and os.path.isdir(os.path.join(REPOS_BASE_PATH, d, ".git"))
        ]

        if not repos:
            message = "Nenhum repositório Git encontrado no diretório base."
            send_telegram_message(chat_id, message)
            return {"status": "success", "data": [], "message": message}

        repos_list = "Repositórios disponíveis:\n\n"
        for i, repo_name in enumerate(repos, 1):
            repos_list += f"{i}. {repo_name}\n"

        repos_list += "\nUse /select <nome_repo> para selecionar um repositório."

        send_telegram_message(chat_id, repos_list)
        return {"status": "success", "data": repos}
    except Exception as e:
        error_msg = f"Erro ao listar repositórios: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/select")
async def select_repo(request: RepoSelectionRequest):
    """Seleciona um repositório para trabalhar."""
    try:
        repo_path = os.path.join(REPOS_BASE_PATH, request.repo_name)

        if not os.path.isdir(repo_path):
            error_msg = f"Repositório '{request.repo_name}' não encontrado."
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        if not os.path.isdir(os.path.join(repo_path, ".git")):
            error_msg = (
                f"O diretório '{request.repo_name}' não é um repositório Git válido."
            )
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        # Configura o repositório atual para o usuário
        user_current_repos[request.chat_id] = {
            "repo_name": request.repo_name,
            "repo_path": repo_path,
            "current_dir": "",  # Caminho relativo dentro do repo, inicialmente vazio (raiz)
        }

        message = f"Repositório '{request.repo_name}' selecionado com sucesso!"
        send_telegram_message(request.chat_id, message)
        return {"status": "success", "message": message}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Erro ao selecionar repositório: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/status")
async def get_status(chat_id: str, repo_name: str = None):
    """Verifica o status do repositório."""
    try:
        repo_instance, error = get_repo_for_user(chat_id, repo_name)
        if error:
            send_telegram_message(chat_id, error)
            raise HTTPException(status_code=400, detail=error)

        await update_repository(repo_instance)
        status = repo_instance.git.status()
        send_telegram_message(chat_id, f"Status do repositório:\n```\n{status}\n```")
        return {"status": "success", "data": status}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Erro ao verificar status: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/suggest")
async def suggest_modification(
    request: FileModificationRequest, background_tasks: BackgroundTasks
):
    """Solicita ao Claude sugestões para modificar um arquivo."""
    try:
        # Obtém o repositório do usuário
        if request.repo_name:
            repo_name = request.repo_name
        elif request.chat_id in user_current_repos:
            repo_name = user_current_repos[request.chat_id]["repo_name"]
        else:
            error_msg = "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        repo_path = os.path.join(REPOS_BASE_PATH, repo_name)
        current_dir = user_current_repos[request.chat_id].get("current_dir", "")

        # Constrói o caminho completo do arquivo
        file_rel_path = os.path.normpath(os.path.join(current_dir, request.file_path))
        full_path = os.path.join(repo_path, file_rel_path)

        # Verifica se o arquivo existe
        if not os.path.exists(full_path):
            error_msg = f"Arquivo não encontrado: {file_rel_path}"
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Informa ao usuário que a consulta está em andamento
        send_telegram_message(
            request.chat_id,
            "Consultando Claude para sugestões de modificação. Aguarde um momento...",
        )

        # Executa a consulta ao Claude em uma tarefa em segundo plano
        background_tasks.add_task(
            process_suggestion_request,
            file_rel_path,
            request.description,
            request.chat_id,
            repo_path,
        )

        return {
            "status": "processing",
            "message": "Processando solicitação de sugestão",
        }

    except Exception as e:
        error_msg = f"Erro ao processar solicitação: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


async def process_suggestion_request(
    file_path: str, description: str, chat_id: str, repo_path: str
):
    """Processa a solicitação de sugestão em segundo plano."""
    try:
        # Lê o conteúdo do arquivo
        full_path = os.path.join(repo_path, file_path)
        with open(full_path, "r", encoding="utf-8") as file:
            content = file.read()

        # Consulta o Claude para sugestões
        prompt = f"""
        Aqui está o conteúdo do arquivo '{file_path}':
        
        ```
        {content}
        ```
        
        Modificação desejada: {description}
        
        Por favor, sugira o código modificado para atender a essa solicitação.
        Forneça apenas o código completo modificado, sem explicações adicionais.
        """

        response = claude.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        suggested_code = response.content[0].text

        # Extrai o código da resposta
        if "```" in suggested_code:
            # Tenta extrair código entre delimitadores de bloco de código
            parts = suggested_code.split("```")
            if len(parts) >= 3:
                # Pega o conteúdo do primeiro bloco de código
                suggested_code = parts[1]
                if suggested_code.startswith(
                    ("python", "javascript", "java", "typescript")
                ):
                    suggested_code = suggested_code.split("\n", 1)[1]

        # Armazena a sugestão
        suggestion_id = str(len(suggestions_store) + 1)
        suggestions_store[suggestion_id] = {
            "file_path": file_path,
            "original": content,
            "suggested": suggested_code,
            "description": description,
            "chat_id": chat_id,
            "repo_path": repo_path,
        }

        # Envia a sugestão para o usuário
        send_telegram_message(
            chat_id,
            f"Sugestão #{suggestion_id} para '{file_path}':\n\n"
            f"```\n{suggested_code[:1000]}...\n```\n\n"
            f"(Mostrando apenas os primeiros 1000 caracteres)\n\n"
            f"Para aplicar: /apply {suggestion_id}\n"
            f"Para rejeitar: /reject {suggestion_id}",
        )

    except Exception as e:
        error_msg = f"Erro ao gerar sugestão: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        logger.error(error_msg)


@app.post("/apply")
async def apply_modification(request: ApplyModificationRequest):
    """Aplica a sugestão proposta pelo Claude."""
    try:
        # Verifica se a sugestão existe
        if request.suggestion_id not in suggestions_store:
            error_msg = f"Sugestão #{request.suggestion_id} não encontrada."
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Obtém os dados da sugestão
        suggestion = suggestions_store[request.suggestion_id]
        file_path = suggestion["file_path"]
        suggested_code = suggestion["suggested"]

        # Aplica a sugestão
        full_path = os.path.join(REPO_PATH, file_path)
        with open(full_path, "w", encoding="utf-8") as file:
            file.write(suggested_code)

        # Informa ao usuário
        send_telegram_message(
            request.chat_id,
            f"Sugestão #{request.suggestion_id} aplicada com sucesso ao arquivo '{file_path}'.\n"
            f"Use /commit para confirmar as alterações.",
        )

        return {
            "status": "success",
            "message": f"Sugestão #{request.suggestion_id} aplicada com sucesso",
        }

    except Exception as e:
        error_msg = f"Erro ao aplicar sugestão: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/reject")
async def reject_modification(request: ApplyModificationRequest):
    """Rejeita a sugestão proposta pelo Claude."""
    try:
        # Verifica se a sugestão existe
        if request.suggestion_id not in suggestions_store:
            error_msg = f"Sugestão #{request.suggestion_id} não encontrada."
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Remove a sugestão
        file_path = suggestions_store[request.suggestion_id]["file_path"]
        del suggestions_store[request.suggestion_id]

        # Informa ao usuário
        send_telegram_message(
            request.chat_id,
            f"Sugestão #{request.suggestion_id} para '{file_path}' foi rejeitada.",
        )

        return {
            "status": "success",
            "message": f"Sugestão #{request.suggestion_id} rejeitada",
        }

    except Exception as e:
        error_msg = f"Erro ao rejeitar sugestão: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/commit")
async def commit_changes(request: CommitRequest):
    """Realiza commit das alterações."""
    try:
        # Adiciona todas as alterações
        repo.git.add("--all")

        # Realiza o commit
        repo.git.commit("-m", request.message)

        # Informa ao usuário
        send_telegram_message(
            request.chat_id,
            f"Commit realizado com sucesso: '{request.message}'.\n"
            f"Use /push para enviar as alterações para o GitHub.",
        )

        return {
            "status": "success",
            "message": f"Commit realizado com sucesso: '{request.message}'",
        }

    except Exception as e:
        error_msg = f"Erro ao realizar commit: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/push")
async def push_changes(request: PushRequest):
    """Envia as alterações para o GitHub."""
    try:
        # Envia as alterações para o GitHub
        origin = repo.remotes.origin
        origin.push()

        # Informa ao usuário
        send_telegram_message(
            request.chat_id, "Alterações enviadas com sucesso para o GitHub."
        )

        return {
            "status": "success",
            "message": "Alterações enviadas com sucesso para o GitHub",
        }

    except Exception as e:
        error_msg = f"Erro ao enviar alterações: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/run_action/{workflow_name}")
async def execute_github_action(workflow_name: str, request: PushRequest):
    """Executa uma GitHub Action específica."""
    try:
        result = run_github_action(workflow_name)

        if result:
            # Informa ao usuário
            send_telegram_message(
                request.chat_id,
                f"GitHub Action '{workflow_name}' iniciada com sucesso.",
            )

            return {
                "status": "success",
                "message": f"GitHub Action '{workflow_name}' iniciada com sucesso",
            }
        else:
            error_msg = f"Erro ao iniciar GitHub Action '{workflow_name}'."
            send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    except Exception as e:
        error_msg = f"Erro ao executar GitHub Action: {str(e)}"
        send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


# Inicia a aplicação
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
