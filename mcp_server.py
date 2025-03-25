import asyncio
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional
import time 
import json
import anthropic
import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from git import Repo
from langchain.chains import LLMChain
from langchain.chat_models import ChatAnthropic
from langchain.prompts import PromptTemplate
from pydantic import BaseModel
from security.encryption import encryption_manager
from security.mcp_security import (
    SecureMiddleware,
    decrypt_request_data,
    encrypt_response_data,
)
from utils.common import get_connection_config, get_repo_info, get_security_config

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

# Armazenamento do repositório atual de cada usuário
user_current_repos = {}
chat_id = None

# Inicializa a aplicação FastAPI
app = FastAPI(title="MCP Server - Gerenciador de Repositório com IA")

# Aplica o middleware de segurança
# app.add_middleware(SecureMiddleware)


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


def run_github_action(workflow_name: str, repo_url: str):
    """Executa uma GitHub Action específica."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Extrai o proprietário e o nome do repositório da URL
    repo_parts = repo_url.split("/")
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

@app.get("/health")
async def health_check():
    """Endpoint para verificação de saúde do servidor."""
    return {
        "status": "healthy",
        "server": "MCP Server",
        "version": "1.0.0",
        "timestamp": int(time.time())
    }


# Rota de teste para desenvolvimento
@app.get("/")
async def root():
    """Rota de teste que não requer autenticação."""
    return {
        "status": "running",
        "message": "MCP Server está em execução. Use endpoints autenticados para operações reais.",
        "docs": "/docs",
        "health": "/health"
    }


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

        # if not repos:
        #     message = "Nenhum repositório Git encontrado no diretório base."
        #     return {"status": "success", "data": [], "message": message}

        repos_list = "Repositórios disponíveis:\n\n"
        for i, repo_name in enumerate(repos, 1):
            repos_list += f"{i}. {repo_name}\n"

        repos_list += "\nUse /select <nome_repo> para selecionar um repositório."

        return {"status": "success", "data": repos}
    except Exception as e:
        error_msg = f"Erro ao listar repositórios: {str(e)}"
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/status")
async def get_status(chat_id: str, repo_name: str = None):
    """Verifica o status do repositório."""
    try:
        repo_instance, error = get_repo_for_user(chat_id, repo_name)
        if error:
            raise HTTPException(status_code=400, detail=error)

        await update_repository(repo_instance)
        status = repo_instance.git.status()
        return {"status": "success", "data": status}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Erro ao verificar status: {str(e)}"
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

@app.get("/ls")
async def list_files(chat_id: str, path: str):
    """Lista arquivos e pastas do diretório especificado."""
    try:
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado."
            )
        
        user_info = user_current_repos[chat_id]
        repo_path = user_info["repo_path"]
        current_rel_dir = user_info.get("current_dir", "")
        
        # Constrói o caminho completo
        target_rel_path = os.path.normpath(os.path.join(current_rel_dir, path)) if path else current_rel_dir
        target_abs_path = os.path.join(repo_path, target_rel_path)
        
        # Verifica se o caminho existe e é um diretório
        if not os.path.isdir(target_abs_path):
            raise HTTPException(
                status_code=404,
                detail=f"Caminho não encontrado ou não é um diretório: {target_rel_path}"
            )
        
        # Lista o conteúdo do diretório
        items = os.listdir(target_abs_path)
        
        # Separa diretórios e arquivos
        directories = []
        files = []
        
        for item in items:
            item_path = os.path.join(target_abs_path, item)
            if os.path.isdir(item_path):
                if item != ".git":  # Opcional: ocultar diretório .git
                    directories.append(f"{item}/")
            else:
                files.append(item)
        
        # Retorna os resultados
        return {
            "status": "success",
            "current_path": target_rel_path or "/",
            "directories": sorted(directories),
            "files": sorted(files)
        }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Erro ao listar diretório: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar diretório: {str(e)}")

@app.post("/select")
async def select_repository(request: Request):
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
                detail="Parâmetros obrigatórios não fornecidos: chat_id e repo_name"
            )
            
        # Constrói o caminho do repositório
        repo_path = os.path.join(REPOS_BASE_PATH, repo_name)
        
        if not os.path.isdir(repo_path):
            raise HTTPException(
                status_code=404,
                detail=f"Repositório '{repo_name}' não encontrado."
            )
        
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            raise HTTPException(
                status_code=400,
                detail=f"O diretório '{repo_name}' não é um repositório Git válido."
            )
        
        # Configura o repositório atual para o usuário
        user_current_repos[chat_id] = {
            "repo_name": repo_name,
            "repo_path": repo_path,
            "current_dir": ""  # Caminho relativo dentro do repo, inicialmente vazio (raiz)
        }
        
        logger.info(f"Repositório '{repo_name}' selecionado para o usuário {chat_id}")
        return {"status": "success", "message": f"Repositório '{repo_name}' selecionado com sucesso!"}

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Erro ao selecionar repositório: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao selecionar repositório: {str(e)}")


def generate_tree(path, prefix="", max_depth=2, current_depth=0):
    """Gera uma representação em árvore de um diretório."""
    if current_depth > max_depth:
        return ""

    result = ""
    items = sorted(os.listdir(path))

    # Filtra itens para excluir o diretório .git
    items = [item for item in items if item != ".git"]

    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        item_path = os.path.join(path, item)

        # Adiciona a linha atual
        if is_last:
            result += f"{prefix}└── {item}\n"
            new_prefix = prefix + "    "
        else:
            result += f"{prefix}├── {item}\n"
            new_prefix = prefix + "│   "

        # Recursão para subdiretórios
        if os.path.isdir(item_path):
            result += generate_tree(item_path, new_prefix, max_depth, current_depth + 1)

    return result

async def getParams(request: Request):
    try:
        # Tenta obter parâmetros de ambas as fontes
        body = {}
        path = None
        
        # Tenta obter do corpo da requisição
        try:
            body_raw = await request.body()
            if body_raw:
                body = json.loads(body_raw)
                chat_id = body.get("chat_id")
                path = body.get("path")
        except:
            # Ignora erros na leitura do corpo
            pass
        
        # Se não encontrou no corpo, tenta obter dos parâmetros de query
        if not chat_id:
            chat_id = request.query_params.get("chat_id")
        if not path:
            path = request.query_params.get("path")
        
        # Verifica se tem os parâmetros necessários
        if not chat_id:
            raise HTTPException(
                status_code=400,
                detail="Parâmetros obrigatórios não fornecidos: chat_id ou path"
            )
        
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado."
            )
        
        return {
            "body": body,
            "chat_id": chat_id,
            "path": path
        }
    except Exception as e:
        await send_telegram_message(chat_id, 
            (f"Erro ao gerar árvore: {str(e)}")
        )
        logger.error(f"Erro ao gerar árvore: {str(e)}")

@app.get("/tree")
async def get_tree(request: Request):
    """Mostra a estrutura de diretórios."""
    try:
        await getParams(request)        
        
        user_info = user_current_repos[chat_id]
        repo_path = user_info["repo_path"]
        max_depth = user_info["max_depth"]
        current_rel_dir = user_info.get("current_dir", "") or "/"
        current_abs_dir = os.path.join(repo_path, current_rel_dir)

        # Gera a árvore
        tree_output = (
            f"📂 {os.path.basename(current_abs_dir) or user_info['repo_name']}\n"
        )
        tree_output += generate_tree(current_abs_dir, "", max_depth)

        # Verifica se a saída não é muito longa para o Telegram
        if len(tree_output) > 4000:
            tree_output = (
                tree_output[:3900] + "\n\n... (saída truncada, use profundidade menor)"
            )

        await send_telegram_message(chat_id,
            f"```\n{tree_output}\n```", parse_mode="Markdown"
        )
    except Exception as e:
        await send_telegram_message(chat_id, 
            (f"Erro ao gerar árvore: {str(e)}")
        )
        logger.error(f"Erro ao gerar árvore: {str(e)}")
        

@app.get("/checkout")
async def checkout_request(chat_id: str):
    """Muda para outra branch."""
    try:
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."

            )
        
        user_info = user_current_repos[chat_id]
        repo_path = user_info["repo_path"]
        args = user_info["args"]
        repo = Repo(repo_path)

        # Lista as branches
        branches = repo.git.branch("-a").split("\n")

        await send_telegram_message(chat_id,
            f"Branches do repositório:\n```\n{chr(10).join(branches)}\n```",
            parse_mode="Markdown",
        )
                
        if not args:
            send_telegram_message(chat_id,
                "Por favor, especifique a branch.\nUso: /checkout <branch>"
            )
            return

        branch_name = args[0]
        repo = Repo(repo_path)
        # Executa o checkout
        repo.git.checkout(branch_name)

        await send_telegram_message(chat_id,
            (f"Alterado para branch: {branch_name}")
        )
    except Exception as e:
        await send_telegram_message(chat_id,
            (f"Erro ao fazer checkout: {str(e)}")
        )
        

@app.get("/branch")
async def branch_request(chat_id: str):
    """Mostra as branches do repositório."""
    try:
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."

            )
        
        user_info = user_current_repos[chat_id]
        repo_path = user_info["repo_path"]
        
        repo = Repo(repo_path)

        # Lista as branches
        branches = repo.git.branch("-a").split("\n")

        await send_telegram_message(chat_id,
            f"Branches do repositório:\n```\n{chr(10).join(branches)}\n```",
            parse_mode="Markdown",
        )
    except Exception as e:
        await send_telegram_message(chat_id,
            (f"Erro ao listar branches: {str(e)}")
        )
    
             

@app.get("/cat")
async def cat_request(chat_id: str):
    """Mostra o conteúdo de um arquivo."""
    try:
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado."
            )
        
        user_info = user_current_repos[chat_id]
        repo_name = user_info["repo_name"]
        repo_path = user_info["repo_path"]
        current_rel_dir = user_info.get("current_dir", "") or "/"
        file_arg = " ".join(user_info.args)     

        # Constrói o caminho do arquivo
        file_rel_path = os.path.normpath(os.path.join(current_rel_dir, file_arg))
        file_abs_path = os.path.join(repo_path, file_rel_path)

        # Verifica se o arquivo existe
        if not os.path.isfile(file_abs_path):
            await send_telegram_message(chat_id,
                (f"Arquivo não encontrado: {file_rel_path}")
            )
            return

        # Verifica o tamanho do arquivo
        file_size = os.path.getsize(file_abs_path)
        if file_size > 1000000:  # 1MB
            await send_telegram_message(chat_id,
                f"O arquivo é muito grande ({file_size / 1000000:.2f} MB). "
                f"Posso mostrar apenas arquivos menores que 1 MB."
            )
            return

        # Determina o tipo de arquivo para formatação adequada
        _, file_ext = os.path.splitext(file_abs_path)

        # Lê o conteúdo do arquivo
        with open(file_abs_path, "r", encoding="utf-8", errors="replace") as file:
            content = file.read()

        # Limita o tamanho do conteúdo
        if len(content) > 4000:
            content = content[:3900] + "\n\n... (conteúdo truncado)"

        # Envia o conteúdo formatado
        language = ""
        if file_ext in [
            ".py",
            ".js",
            ".java",
            ".c",
            ".cpp",
            ".cs",
            ".php",
            ".go",
            ".ts",
            ".html",
            ".css",
            ".json",
            ".xml",
        ]:
            language = file_ext[1:]  # Remove o ponto

        message = f"📄 {file_rel_path}:\n\n```{language}\n{content}\n```"

        await send_telegram_message(chat_id, message, parse_mode="Markdown")
    except Exception as e:
        await send_telegram_message(chat_id,
            (f"Erro ao mostrar arquivo: {str(e)}")
        )
        logger.error(f"Erro ao mostrar arquivo: {str(e)}")
        

@app.post("/pwd")
async def get_current_directory(chat_id: str):
    """Mostra o diretório atual."""
    try:
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado."
            )
        
        user_info = user_current_repos[chat_id]
        repo_name = user_info["repo_name"]
        repo_path = user_info["repo_path"]
        current_dir = user_info.get("current_dir", "") or "/"
        
        return {
            "status": "success", 
            "repo_name": repo_name,
            "repo_path": repo_path,
            "current_path": current_dir
        }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Erro ao obter diretório atual: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter diretório atual: {str(e)}")

@app.post("/cd")
async def change_directory(chat_id: str, path: str):
    """Navega para o diretório especificado."""
    try:
        # Verifica se um repositório foi selecionado
        if chat_id not in user_current_repos:
            raise HTTPException(
                status_code=400,
                detail="Nenhum repositório selecionado."
            )
        
        user_info = user_current_repos[chat_id]
        repo_path = user_info["repo_path"]
        current_rel_dir = user_info.get("current_dir", "")
        
        # Caso especial para voltar à raiz
        if path == "/":
            user_current_repos[chat_id]["current_dir"] = ""
            return {"status": "success", "current_path": "/"}
        
        # Caso especial para voltar um nível
        if path == "..":
            new_rel_dir = os.path.dirname(current_rel_dir)
            user_current_repos[chat_id]["current_dir"] = new_rel_dir
            return {"status": "success", "current_path": new_rel_dir or "/"}
        
        # Caso normal
        new_rel_dir = os.path.normpath(os.path.join(current_rel_dir, path))
        new_abs_dir = os.path.join(repo_path, new_rel_dir)
        
        # Verifica se o caminho existe e é um diretório
        if not os.path.isdir(new_abs_dir):
            raise HTTPException(
                status_code=404,
                detail=f"Caminho não encontrado ou não é um diretório: {new_rel_dir}"
            )
        
        # Atualiza o diretório atual
        user_current_repos[chat_id]["current_dir"] = new_rel_dir
        
        return {"status": "success", "current_path": new_rel_dir or "/"}
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"Erro ao navegar para o diretório: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao navegar para o diretório: {str(e)}")

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
            send_telegram_message(chat_id, error_msg)
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
        send_telegram_message(
            chat_id,
            f"Sugestão #{request.suggestion_id} aplicada com sucesso ao arquivo '{file_path}'.\n"
            f"Use /commit para confirmar as alterações.",
        )

        return {
            "status": "success",
            "message": f"Sugestão #{request.suggestion_id} aplicada com sucesso",
        }

    except Exception as e:
        error_msg = f"Erro ao aplicar sugestão: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/reject")
async def reject_modification(request: ApplyModificationRequest):
    """Rejeita a sugestão proposta pelo Claude."""
    try:
        # Verifica se a sugestão existe
        if request.suggestion_id not in suggestions_store:
            error_msg = f"Sugestão #{request.suggestion_id} não encontrada."
            send_telegram_message(chat_id, error_msg)
            raise HTTPException(status_code=404, detail=error_msg)

        # Remove a sugestão
        file_path = suggestions_store[request.suggestion_id]["file_path"]
        del suggestions_store[request.suggestion_id]

        # Informa ao usuário
        send_telegram_message(
            chat_id,
            f"Sugestão #{request.suggestion_id} para '{file_path}' foi rejeitada.",
        )

        return {
            "status": "success",
            "message": f"Sugestão #{request.suggestion_id} rejeitada",
        }

    except Exception as e:
        error_msg = f"Erro ao rejeitar sugestão: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/commit")
async def commit_changes(request: CommitRequest):
    """Realiza commit das alterações."""
    try:
        repo_instance, error = get_repo_for_user(chat_id, request.repo_name)
        if error:
            send_telegram_message(chat_id, error)
            raise HTTPException(status_code=400, detail=error)

        # Adiciona todas as alterações
        repo_instance.git.add("--all")

        # Realiza o commit
        repo_instance.git.commit("-m", request.message)

        # Informa ao usuário
        send_telegram_message(
            chat_id,
            f"Commit realizado com sucesso: '{request.message}'.\n"
            f"Use /push para enviar as alterações para o GitHub.",
        )

        return {
            "status": "success",
            "message": f"Commit realizado com sucesso: '{request.message}'",
        }

    except Exception as e:
        error_msg = f"Erro ao realizar commit: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/push")
async def push_changes(request: PushRequest):
    """Envia as alterações para o GitHub."""
    try:
        repo_instance, error = get_repo_for_user(chat_id, request.repo_name)
        if error:
            send_telegram_message(chat_id, error)
            raise HTTPException(status_code=400, detail=error)

        # Envia as alterações para o GitHub
        origin = repo_instance.remotes.origin
        origin.push()

        # Informa ao usuário
        send_telegram_message(
            chat_id, "Alterações enviadas com sucesso para o GitHub."
        )

        return {
            "status": "success",
            "message": "Alterações enviadas com sucesso para o GitHub",
        }

    except Exception as e:
        error_msg = f"Erro ao enviar alterações: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/run_action/{workflow_name}")
async def execute_github_action(workflow_name: str, request: PushRequest):
    """Executa uma GitHub Action específica."""
    try:
        repo_instance, error = get_repo_for_user(chat_id, request.repo_name)
        if error:
            send_telegram_message(chat_id, error)
            raise HTTPException(status_code=400, detail=error)

        # Obtém a URL remota do repositório
        repo_url = repo_instance.remotes.origin.url

        result = run_github_action(workflow_name, repo_url)

        if result:
            # Informa ao usuário
            send_telegram_message(
                chat_id,
                f"GitHub Action '{workflow_name}' iniciada com sucesso.",
            )

            return {
                "status": "success",
                "message": f"GitHub Action '{workflow_name}' iniciada com sucesso",
            }
        else:
            error_msg = f"Erro ao iniciar GitHub Action '{workflow_name}'."
            send_telegram_message(chat_id, error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    except Exception as e:
        error_msg = f"Erro ao executar GitHub Action: {str(e)}"
        send_telegram_message(chat_id, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


# Inicia a aplicação
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


#    "/tree", tree_command))
#    "/cat", cat_command))

#    "/branch", branch_command))
#    "/checkout", checkout_command))
#    "/suggest", suggest_command))
#    "/apply", apply_command))
#    "/reject", reject_command))
#    "/commit", commit_command))
#    "/push", push_command))