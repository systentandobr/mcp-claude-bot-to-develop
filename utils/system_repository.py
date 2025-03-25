import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from git import Repo

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class SystemRepository:
    def __init__(self, base_path: str, github_token: str):
        self.base_path = base_path
        self.github_token = github_token
        # Armazenamento do repositório atual de cada usuário
        self.user_current_repos = {}

    def get_repo_for_user(
        self, chat_id: str, repo_name: str = None
    ) -> Tuple[Optional[Repo], Optional[str]]:
        """Obtém o repositório atual do usuário."""
        if chat_id not in self.user_current_repos:
            return (
                None,
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um.",
            )

        if repo_name:
            # Busca o repositório especificado
            repo_path = os.path.join(self.base_path, repo_name)
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
            repo_info = self.user_current_repos[chat_id]
            return Repo(repo_info["repo_path"]), None

    async def update_repository(self, repo_instance) -> bool:
        """Atualiza o repositório local com as alterações remotas."""
        try:
            origin = repo_instance.remotes.origin
            origin.pull()
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar repositório: {str(e)}")
            return False

    def run_github_action(self, workflow_name: str, repo_url: str) -> bool:
        """Executa uma GitHub Action específica."""
        import requests

        headers = {
            "Authorization": f"token {self.github_token}",
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

    def list_repos(self) -> List[str]:
        """Lista todos os repositórios disponíveis."""
        try:
            # Lista todos os diretórios no caminho base que são repositórios Git
            repos = [
                d
                for d in os.listdir(self.base_path)
                if os.path.isdir(os.path.join(self.base_path, d))
                and os.path.isdir(os.path.join(self.base_path, d, ".git"))
            ]
            return repos
        except Exception as e:
            logger.error(f"Erro ao listar repositórios: {str(e)}")
            return []

    def select_repository(self, chat_id: str, repo_name: str) -> Dict[str, str]:
        """Seleciona um repositório para trabalhar."""
        try:
            # Constrói o caminho do repositório
            repo_path = os.path.join(self.base_path, repo_name)

            if not os.path.isdir(repo_path):
                return {
                    "status": "error",
                    "message": f"Repositório '{repo_name}' não encontrado.",
                }

            if not os.path.isdir(os.path.join(repo_path, ".git")):
                return {
                    "status": "error",
                    "message": f"O diretório '{repo_name}' não é um repositório Git válido.",
                }

            # Configura o repositório atual para o usuário
            self.user_current_repos[chat_id] = {
                "repo_name": repo_name,
                "repo_path": repo_path,
                "current_dir": "",  # Caminho relativo dentro do repo, inicialmente vazio (raiz)
            }

            logger.info(
                f"Repositório '{repo_name}' selecionado para o usuário {chat_id}"
            )
            return {
                "status": "success",
                "message": f"Repositório '{repo_name}' selecionado com sucesso!",
            }
        except Exception as e:
            logger.error(f"Erro ao selecionar repositório: {str(e)}")
            return {
                "status": "error",
                "message": f"Erro ao selecionar repositório: {str(e)}",
            }

    def list_files(self, chat_id: str, path: str = "") -> Dict[str, Any]:
        """Lista arquivos e pastas do diretório especificado."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]
            current_rel_dir = user_info.get("current_dir", "")

            # Constrói o caminho completo
            target_rel_path = (
                os.path.normpath(os.path.join(current_rel_dir, path))
                if path
                else current_rel_dir
            )
            target_abs_path = os.path.join(repo_path, target_rel_path)

            # Verifica se o caminho existe e é um diretório
            if not os.path.isdir(target_abs_path):
                return {
                    "status": "error",
                    "message": f"Caminho não encontrado ou não é um diretório: {target_rel_path}",
                }

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
                "files": sorted(files),
            }
        except Exception as e:
            logger.error(f"Erro ao listar diretório: {str(e)}")
            return {"status": "error", "message": f"Erro ao listar diretório: {str(e)}"}

    def change_directory(self, chat_id: str, path: str) -> Dict[str, str]:
        """Navega para o diretório especificado."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]
            current_rel_dir = user_info.get("current_dir", "")

            # Caso especial para voltar à raiz
            if path == "/":
                self.user_current_repos[chat_id]["current_dir"] = ""
                return {"status": "success", "current_path": "/"}

            # Caso especial para voltar um nível
            if path == "..":
                new_rel_dir = os.path.dirname(current_rel_dir)
                self.user_current_repos[chat_id]["current_dir"] = new_rel_dir
                return {"status": "success", "current_path": new_rel_dir or "/"}

            # Caso normal
            new_rel_dir = os.path.normpath(os.path.join(current_rel_dir, path))
            new_abs_dir = os.path.join(repo_path, new_rel_dir)

            # Verifica se o caminho existe e é um diretório
            if not os.path.isdir(new_abs_dir):
                return {
                    "status": "error",
                    "message": f"Caminho não encontrado ou não é um diretório: {new_rel_dir}",
                }

            # Atualiza o diretório atual
            self.user_current_repos[chat_id]["current_dir"] = new_rel_dir

            return {"status": "success", "current_path": new_rel_dir or "/"}
        except Exception as e:
            logger.error(f"Erro ao navegar para o diretório: {str(e)}")
            return {
                "status": "error",
                "message": f"Erro ao navegar para o diretório: {str(e)}",
            }

    def get_current_directory(self, chat_id: str) -> Dict[str, str]:
        """Obtém o diretório atual."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_name = user_info["repo_name"]
            repo_path = user_info["repo_path"]
            current_dir = user_info.get("current_dir", "") or "/"

            return {
                "status": "success",
                "repo_name": repo_name,
                "repo_path": repo_path,
                "current_path": current_dir,
            }
        except Exception as e:
            logger.error(f"Erro ao obter diretório atual: {str(e)}")
            return {
                "status": "error",
                "message": f"Erro ao obter diretório atual: {str(e)}",
            }

    def generate_tree(self, path, prefix="", max_depth=2, current_depth=0):
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
                result += self.generate_tree(
                    item_path, new_prefix, max_depth, current_depth + 1
                )

        return result

    def get_tree(self, chat_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """Obtém a estrutura de diretórios em formato de árvore."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]
            current_rel_dir = user_info.get("current_dir", "") or "/"
            current_abs_dir = os.path.join(repo_path, current_rel_dir)

            # Gera a árvore
            tree_header = (
                f"📂 {os.path.basename(current_abs_dir) or user_info['repo_name']}\n"
            )
            tree_content = self.generate_tree(current_abs_dir, "", max_depth)
            tree_output = tree_header + tree_content

            # Verifica se a saída não é muito longa para o Telegram
            if len(tree_output) > 4000:
                tree_output = (
                    tree_output[:3900]
                    + "\n\n... (saída truncada, use profundidade menor)"
                )

            return {"status": "success", "tree": tree_output}
        except Exception as e:
            logger.error(f"Erro ao gerar árvore: {str(e)}")
            return {"status": "error", "message": f"Erro ao gerar árvore: {str(e)}"}

    def get_file_content(self, chat_id: str, file_path: str) -> Dict[str, Any]:
        """Obtém o conteúdo de um arquivo."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]
            current_rel_dir = user_info.get("current_dir", "")

            # Constrói o caminho do arquivo
            file_rel_path = os.path.normpath(os.path.join(current_rel_dir, file_path))
            file_abs_path = os.path.join(repo_path, file_rel_path)

            # Verifica se o arquivo existe
            if not os.path.isfile(file_abs_path):
                return {
                    "status": "error",
                    "message": f"Arquivo não encontrado: {file_rel_path}",
                }

            # Verifica o tamanho do arquivo
            file_size = os.path.getsize(file_abs_path)
            if file_size > 1000000:  # 1MB
                return {
                    "status": "error",
                    "message": f"O arquivo é muito grande ({file_size / 1000000:.2f} MB). Posso mostrar apenas arquivos menores que 1 MB.",
                }

            # Determina o tipo de arquivo para formatação adequada
            _, file_ext = os.path.splitext(file_abs_path)
            file_type = file_ext[1:] if file_ext else ""

            # Lê o conteúdo do arquivo
            with open(file_abs_path, "r", encoding="utf-8", errors="replace") as file:
                content = file.read()

            return {
                "status": "success",
                "file_path": file_rel_path,
                "file_type": file_type,
                "content": content,
            }
        except Exception as e:
            logger.error(f"Erro ao mostrar arquivo: {str(e)}")
            return {"status": "error", "message": f"Erro ao mostrar arquivo: {str(e)}"}

    def get_branches(self, chat_id: str) -> Dict[str, Any]:
        """Obtém as branches do repositório."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]

            repo = Repo(repo_path)

            # Lista as branches
            branches = repo.git.branch("-a").split("\n")

            return {"status": "success", "branches": branches}
        except Exception as e:
            logger.error(f"Erro ao listar branches: {str(e)}")
            return {"status": "error", "message": f"Erro ao listar branches: {str(e)}"}

    def checkout_branch(self, chat_id: str, branch_name: str) -> Dict[str, str]:
        """Faz checkout para uma branch."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]

            repo = Repo(repo_path)

            # Executa o checkout
            repo.git.checkout(branch_name)

            return {
                "status": "success",
                "message": f"Alterado para branch: {branch_name}",
            }
        except Exception as e:
            logger.error(f"Erro ao fazer checkout: {str(e)}")
            return {"status": "error", "message": f"Erro ao fazer checkout: {str(e)}"}

    def get_status(self, chat_id: str) -> Dict[str, Any]:
        """Verifica o status do repositório."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]

            repo = Repo(repo_path)

            # Obtém o status
            status = repo.git.status()

            return {"status": "success", "data": status}
        except Exception as e:
            logger.error(f"Erro ao verificar status: {str(e)}")
            return {"status": "error", "message": f"Erro ao verificar status: {str(e)}"}

    def commit_changes(self, chat_id: str, message: str) -> Dict[str, str]:
        """Realiza commit das alterações."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]

            repo = Repo(repo_path)

            # Adiciona todas as alterações
            repo.git.add("--all")

            # Realiza o commit
            repo.git.commit("-m", message)

            return {
                "status": "success",
                "message": f"Commit realizado com sucesso: '{message}'",
            }
        except Exception as e:
            logger.error(f"Erro ao realizar commit: {str(e)}")
            return {"status": "error", "message": f"Erro ao realizar commit: {str(e)}"}

    def push_changes(self, chat_id: str) -> Dict[str, str]:
        """Envia as alterações para o GitHub."""
        try:
            # Verifica se um repositório foi selecionado
            if chat_id not in self.user_current_repos:
                return {"status": "error", "message": "Nenhum repositório selecionado."}

            user_info = self.user_current_repos[chat_id]
            repo_path = user_info["repo_path"]

            repo = Repo(repo_path)

            # Envia as alterações para o GitHub
            origin = repo.remotes.origin
            origin.push()

            return {
                "status": "success",
                "message": "Alterações enviadas com sucesso para o GitHub",
            }
        except Exception as e:
            logger.error(f"Erro ao enviar alterações: {str(e)}")
            return {
                "status": "error",
                "message": f"Erro ao enviar alterações: {str(e)}",
            }
