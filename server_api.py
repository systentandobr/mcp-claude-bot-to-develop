import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from security.mcp_security import SecureMiddleware, get_api_key
from utils.common import get_connection_config, get_repo_info, get_security_config
from utils.system_repository import SystemRepository

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carrega configurações usando as funções de utilitário
connection_config = get_connection_config()
repo_config = get_repo_info()
security_config = get_security_config()

# Configuração das chaves de API
CLAUDE_API_KEY = connection_config["claude_api_key"]
GITHUB_TOKEN = repo_config["github_token"]
REPOS_BASE_PATH = repo_config["repos_base_path"]
MCP_API_KEY = security_config["mcp_api_key"]
TELEGRAM_BOT_TOKEN = connection_config["telegram_token"]

# Inicializa o cliente Claude
claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# Inicializa o gestor de repositórios
system_repo = SystemRepository(REPOS_BASE_PATH, GITHUB_TOKEN)

# Armazenamento de sugestões
suggestions_store = {}


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


# Função para enviar mensagens pelo Telegram
async def send_telegram_message(chat_id: str, text: str, parse_mode: str = None):
    """Função para enviar mensagens pelo Telegram."""
    import requests

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
    }

    if parse_mode:
        data["parse_mode"] = parse_mode

    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para o Telegram: {str(e)}")
        return None


# Define o roteador FastAPI
router = APIRouter()


@router.get("/health")
async def health_check():
    """Endpoint para verificação de saúde do servidor."""
    return {
        "status": "healthy",
        "server": "MCP Server",
        "version": "1.0.0",
        "timestamp": int(time.time()),
    }


@router.get("/")
async def root():
    """Rota de teste que não requer autenticação."""
    return {
        "status": "running",
        "message": "MCP Server está em execução. Use endpoints autenticados para operações reais.",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/repos")
async def list_repos(chat_id: str, api_key: str = Depends(get_api_key)):
    """Lista todos os repositórios disponíveis."""
    try:
        repos = system_repo.list_repos()
        return {"status": "success", "repos": repos}
    except Exception as e:
        error_msg = f"Erro ao listar repositórios: {str(e)}"
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/status")
async def get_status(
    chat_id: str, repo_name: str = None, api_key: str = Depends(get_api_key)
):
    """Verifica o status do repositório."""
    return system_repo.get_status(chat_id)


@router.post("/suggest")
async def suggest_modification(
    request: FileModificationRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key),
):
    """Solicita ao Claude sugestões para modificar um arquivo."""
    try:
        # Obtém o repositório do usuário
        if request.repo_name:
            repo_name = request.repo_name
        elif request.chat_id in system_repo.user_current_repos:
            repo_name = system_repo.user_current_repos[request.chat_id]["repo_name"]
        else:
            error_msg = "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            await send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        repo_path = os.path.join(REPOS_BASE_PATH, repo_name)
        current_dir = system_repo.user_current_repos[request.chat_id].get(
            "current_dir", ""
        )

        # Constrói o caminho completo do arquivo
        file_rel_path = os.path.normpath(os.path.join(current_dir, request.file_path))
        full_path = os.path.join(repo_path, file_rel_path)

        # Verifica se o arquivo existe
        if not os.path.exists(full_path):
            error_msg = f"Arquivo não encontrado: {file_rel_path}"
            await send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Informa ao usuário que a consulta está em andamento
        await send_telegram_message(
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
        await send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/ls")
async def list_files(chat_id: str, path: str = "", api_key: str = Depends(get_api_key)):
    """Lista arquivos e pastas do diretório especificado."""
    return system_repo.list_files(chat_id, path)


@router.post("/select")
async def select_repository(request: Request, api_key: str = Depends(get_api_key)):
    """Seleciona um repositório para trabalhar."""
    try:
        # Tenta obter parâmetros de ambas as fontes
        body = {}
        chat_id = None
        repo_name = None

        # Tenta obter do corpo da requisição
        try:
            body_raw = await request.body()
            if body_raw:
                body = json.loads(body_raw)
                chat_id = body.get("chat_id")
                repo_name = body.get("repo_name")
        except:
            # Ignora erros na leitura do corpo
            pass

        # Se não encontrou no corpo, tenta obter dos parâmetros de query
        if not chat_id:
            chat_id = request.query_params.get("chat_id")
        if not repo_name:
            repo_name = request.query_params.get("repo_name")

        # Verifica se tem os parâmetros necessários
        if not chat_id or not repo_name:
            raise HTTPException(
                status_code=400,
                detail="Parâmetros obrigatórios não fornecidos: chat_id e repo_name",
            )

        return system_repo.select_repository(chat_id, repo_name)
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Erro ao selecionar repositório: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao selecionar repositório: {str(e)}"
        )


@router.get("/tree")
async def get_tree(
    chat_id: str, max_depth: int = 2, api_key: str = Depends(get_api_key)
):
    """Mostra a estrutura de diretórios."""
    return system_repo.get_tree(chat_id, max_depth)


@router.get("/cat")
async def get_file_content(
    chat_id: str, file_path: str, api_key: str = Depends(get_api_key)
):
    """Mostra o conteúdo de um arquivo."""
    return system_repo.get_file_content(chat_id, file_path)


@router.post("/pwd")
async def get_current_directory(chat_id: str, api_key: str = Depends(get_api_key)):
    """Mostra o diretório atual."""
    return system_repo.get_current_directory(chat_id)


@router.post("/cd")
async def change_directory(
    chat_id: str, path: str, api_key: str = Depends(get_api_key)
):
    """Navega para o diretório especificado."""
    return system_repo.change_directory(chat_id, path)


@router.get("/branch")
async def get_branches(chat_id: str, api_key: str = Depends(get_api_key)):
    """Mostra as branches do repositório."""
    return system_repo.get_branches(chat_id)


@router.get("/checkout")
async def checkout_branch(
    chat_id: str, branch_name: str, api_key: str = Depends(get_api_key)
):
    """Muda para outra branch."""
    return system_repo.checkout_branch(chat_id, branch_name)


@router.post("/apply")
async def apply_modification(
    request: ApplyModificationRequest, api_key: str = Depends(get_api_key)
):
    """Aplica a sugestão proposta pelo Claude."""
    try:
        # Verifica se a sugestão existe
        if request.suggestion_id not in suggestions_store:
            error_msg = f"Sugestão #{request.suggestion_id} não encontrada."
            await send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Obtém os dados da sugestão
        suggestion = suggestions_store[request.suggestion_id]
        file_path = suggestion["file_path"]
        suggested_code = suggestion["suggested"]
        repo_path = suggestion["repo_path"]

        # Aplica a sugestão
        full_path = os.path.join(repo_path, file_path)
        with open(full_path, "w", encoding="utf-8") as file:
            file.write(suggested_code)

        # Informa ao usuário
        await send_telegram_message(
            request.chat_id,
            f"Sugestão #{request.suggestion_id} aplicada com sucesso ao arquivo '{file_path}'.\n"
            f"Use /commit para confirmar as alterações.",
        )

        return {
            "status": "success",
            "message": f"Sugestão #{request.suggestion_id} aplicada com sucesso",
            "file_path": file_path,
        }

    except Exception as e:
        error_msg = f"Erro ao aplicar sugestão: {str(e)}"
        await send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/reject")
async def reject_modification(
    request: ApplyModificationRequest, api_key: str = Depends(get_api_key)
):
    """Rejeita a sugestão proposta pelo Claude."""
    try:
        # Verifica se a sugestão existe
        if request.suggestion_id not in suggestions_store:
            error_msg = f"Sugestão #{request.suggestion_id} não encontrada."
            await send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Remove a sugestão
        file_path = suggestions_store[request.suggestion_id]["file_path"]
        del suggestions_store[request.suggestion_id]

        # Informa ao usuário
        await send_telegram_message(
            request.chat_id,
            f"Sugestão #{request.suggestion_id} para '{file_path}' foi rejeitada.",
        )

        return {
            "status": "success",
            "message": f"Sugestão #{request.suggestion_id} rejeitada",
            "file_path": file_path,
        }

    except Exception as e:
        error_msg = f"Erro ao rejeitar sugestão: {str(e)}"
        await send_telegram_message(request.chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/commit")
async def commit_changes(request: CommitRequest, api_key: str = Depends(get_api_key)):
    """Realiza commit das alterações."""
    return system_repo.commit_changes(request.chat_id, request.message)


@router.post("/push")
async def push_changes(request: PushRequest, api_key: str = Depends(get_api_key)):
    """Envia as alterações para o GitHub."""
    return system_repo.push_changes(request.chat_id)


@router.post("/run_action/{workflow_name}")
async def execute_github_action(
    workflow_name: str, request: PushRequest, api_key: str = Depends(get_api_key)
):
    """Executa uma GitHub Action específica."""
    try:
        repo_instance, error = system_repo.get_repo_for_user(
            request.chat_id, request.repo_name
        )
        if error:
            await send_telegram_message(request.chat_id, error)
            raise HTTPException(status_code=400, detail=error)

        # Obtém a URL remota do repositório
        repo_url = repo_instance.remotes.origin.url

        result = system_repo.run_github_action(workflow_name, repo_url)

        if result:
            # Informa ao usuário
            await send_telegram_message(
                request.chat_id,
                f"GitHub Action '{workflow_name}' iniciada com sucesso.",
            )

            return {
                "status": "success",
                "message": f"GitHub Action '{workflow_name}' iniciada com sucesso",
            }
        else:
            error_msg = f"Erro ao iniciar GitHub Action '{workflow_name}'."
            await send_telegram_message(request.chat_id, error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    except Exception as e:
        error_msg = f"Erro ao executar GitHub Action: {str(e)}"
        await send_telegram_message(request.chat_id, error_msg)
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
            model="claude-3-7-sonnet-20250219",
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
        await send_telegram_message(
            chat_id,
            f"Sugestão #{suggestion_id} para '{file_path}':\n\n"
            f"```\n{suggested_code[:1000]}...\n```\n\n"
            f"(Mostrando apenas os primeiros 1000 caracteres)\n\n"
            f"Para aplicar: /apply {suggestion_id}\n"
            f"Para rejeitar: /reject {suggestion_id}",
            parse_mode="Markdown",
        )

    except Exception as e:
        error_msg = f"Erro ao gerar sugestão: {str(e)}"
        await send_telegram_message(chat_id, error_msg)
        logger.error(error_msg)


import os
