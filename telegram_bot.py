import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from screenshot_utils import capture_directory_structure, capture_file_content
from security.secure_mcp_client import SecureMCPClient
from utils.common import get_connection_config, get_env_var

# Configuração de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Carrega configurações usando a função de utilitário
config = get_connection_config()
TELEGRAM_TOKEN = config["telegram_token"]
MCP_HOST = config["mcp_host"]
MCP_PORT = config["mcp_port"]

# Inicializa o cliente MCP
mcp_client = SecureMCPClient()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia mensagem quando o comando /start é emitido."""
    await update.message.reply_text(
        "Olá! Sou seu assistente de desenvolvimento. Posso te ajudar a modificar "
        "seu repositório GitHub usando o Claude. Use /help para ver os comandos disponíveis."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia mensagem de ajuda quando o comando /help é emitido."""
    help_text = """
    Comandos disponíveis:
    /start - Inicia o bot
    /help - Mostra esta mensagem de ajuda

    Navegação:
    /repos - Lista todos os repositórios disponíveis
    /select <nome_repo> - Seleciona um repositório para trabalhar
    /ls [caminho] - Lista arquivos e pastas do diretório atual ou do caminho especificado
    /cd <caminho> - Navega para o diretório especificado
    /pwd - Mostra o diretório atual
    /tree [profundidade] - Mostra a estrutura de diretórios (padrão: profundidade 2)
    /cat <arquivo> - Mostra o conteúdo de um arquivo

    Manipulação de código:
    /status - Verifica o status do repositório atual
    /suggest <arquivo> <descrição> - Solicita ao Claude sugestões para modificar um arquivo
    /apply <id_sugestão> - Aplica a sugestão proposta
    /reject <id_sugestão> - Rejeita a sugestão proposta
    /commit <mensagem> - Realiza commit das alterações
    /push - Envia as alterações para o GitHub
    /branch - Mostra as branches do repositório
    /checkout <branch> - Muda para outra branch
    """
    await update.message.reply_text(help_text)


async def repos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista todos os repositórios disponíveis."""
    try:
        user_id = str(update.effective_user.id)

        # Consulta o MCP Server para listar os repositórios
        response = mcp_client.list_repos(user_id)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao listar repositórios: {response['error']}"
            )
            return

        repos = response.get("repos", [])

        repos_list = "Repositórios disponíveis:\n\n"
        for i, repo_name in enumerate(repos, 1):
            repos_list += f"{i}. {repo_name}\n"

        repos_list += "\nUse /select <nome_repo> para selecionar um repositório."

        await update.message.reply_text(repos_list)
    except Exception as e:
        await update.message.reply_text(f"Erro ao listar repositórios: {str(e)}")


async def select_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Seleciona um repositório para trabalhar."""
    try:
        user_id = str(update.effective_user.id)

        if not context.args:
            await update.message.reply_text(
                "Por favor, especifique o nome do repositório.\nUso: /select <nome_repo>"
            )
            return

        repo_name = context.args[0]

        # Solicita ao MCP Server para selecionar o repositório
        response = mcp_client.select_repo(user_id, repo_name)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao selecionar repositório: {response['error']}"
            )
            return

        if response.get("status") == "success":
            await update.message.reply_text(
                f"Repositório '{repo_name}' selecionado com sucesso!\n"
                f"Use /ls para listar arquivos e diretórios ou /status para ver o status do Git."
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao selecionar repositório.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao selecionar repositório: {str(e)}")


async def ls_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista arquivos e pastas do diretório atual ou do caminho especificado."""
    try:
        user_id = str(update.effective_user.id)
        path_arg = " ".join(context.args) if context.args else ""

        # Consulta o MCP Server para listar os arquivos
        response = mcp_client.list_files(user_id, path_arg)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao listar diretório: {response['error']}"
            )
            return

        if response.get("status") == "error":
            await update.message.reply_text(
                response.get("message", "Erro ao listar diretório.")
            )
            return

        # Formata e envia a resposta
        directories = response.get("directories", [])
        files = response.get("files", [])
        current_path = response.get("current_path", "/")

        message = f"📂 Conteúdo de '{current_path}':\n\n"

        if directories:
            message += (
                "Diretórios:\n" + "\n".join([f"📁 {d}" for d in directories]) + "\n\n"
            )

        if files:
            message += "Arquivos:\n" + "\n".join([f"📄 {f}" for f in files])

        if not directories and not files:
            message += "Diretório vazio"

        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Erro ao listar diretório: {str(e)}")


async def cd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Navega para o diretório especificado."""
    try:
        user_id = str(update.effective_user.id)

        if not context.args:
            await update.message.reply_text(
                "Por favor, especifique o caminho.\nUso: /cd <caminho>"
            )
            return

        path_arg = " ".join(context.args)

        # Solicita ao MCP Server para mudar o diretório
        response = mcp_client.change_directory(user_id, path_arg, context.args)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao navegar para o diretório: {response['error']}"
            )
            return

        if response.get("status") == "success":
            new_path = response.get("current_path", "/")
            await update.message.reply_text(f"Navegado para '{new_path}'")
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao navegar para o diretório.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao navegar para o diretório: {str(e)}")


async def pwd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o diretório atual."""
    try:
        user_id = str(update.effective_user.id)

        # Consulta o MCP Server para obter o diretório atual
        response = mcp_client.get_current_directory(user_id, context.args)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao mostrar diretório atual: {response['error']}"
            )
            return

        if response.get("status") == "success":
            repo_name = response.get("repo_name", "")
            current_dir = response.get("current_path", "/")

            await update.message.reply_text(
                f"Repositório: {repo_name}\n" f"Diretório atual: {current_dir}"
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao mostrar diretório atual.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao mostrar diretório atual: {str(e)}")


async def tree_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra a estrutura de diretórios."""
    try:
        user_id = str(update.effective_user.id)

        # Determina a profundidade
        max_depth = 2  # Padrão
        if context.args:
            try:
                max_depth = int(context.args[0])
                # Limita a profundidade para evitar mensagens muito grandes
                if max_depth > 4:
                    max_depth = 4
                    await update.message.reply_text(
                        "Profundidade máxima limitada a 4 para evitar excesso de dados."
                    )
            except ValueError:
                await update.message.reply_text(
                    "Profundidade inválida. Usando valor padrão (2)."
                )

        # Consulta o MCP Server para obter a estrutura de diretórios
        response = mcp_client.get_tree(user_id, max_depth, context.args)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao gerar árvore: {response['error']}"
            )
            return

        if response.get("status") == "success":
            tree_output = response.get("tree", "")

            # Verifica se a saída não é muito longa para o Telegram
            if len(tree_output) > 4000:
                tree_output = (
                    tree_output[:3900]
                    + "\n\n... (saída truncada, use profundidade menor)"
                )

            await update.message.reply_text(
                f"```\n{tree_output}\n```", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao gerar árvore.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao gerar árvore: {str(e)}")


async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o conteúdo de um arquivo."""
    try:
        user_id = str(update.effective_user.id)

        if not context.args:
            await update.message.reply_text(
                "Por favor, especifique o arquivo.\nUso: /cat <arquivo>"
            )
            return

        file_path = " ".join(context.args)

        # Consulta o MCP Server para obter o conteúdo do arquivo
        response = mcp_client.get_file_content(user_id, file_path)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao mostrar arquivo: {response['error']}"
            )
            return

        if response.get("status") == "success":
            content = response.get("content", "")
            file_type = response.get("file_type", "")
            file_path = response.get("file_path", "")

            # Limita o tamanho do conteúdo
            if len(content) > 4000:
                content = content[:3900] + "\n\n... (conteúdo truncado)"

            # Determina o tipo de arquivo para formatação adequada
            language = ""
            if file_type in [
                "py",
                "js",
                "java",
                "c",
                "cpp",
                "cs",
                "php",
                "go",
                "ts",
                "html",
                "css",
                "json",
                "xml",
            ]:
                language = file_type

            message = f"📄 {file_path}:\n\n```{language}\n{content}\n```"

            await update.message.reply_text(message, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao mostrar arquivo.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao mostrar arquivo: {str(e)}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verifica o status do repositório."""
    try:
        user_id = str(update.effective_user.id)

        # Consulta o MCP Server para obter o status do repositório
        response = mcp_client.get_status(user_id)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao verificar status: {response['error']}"
            )
            return

        if response.get("status") == "success":
            git_status = response.get("data", "")

            await update.message.reply_text(
                f"Status do repositório:\n```\n{git_status}\n```", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao verificar status.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao verificar status: {str(e)}")


async def branch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra as branches do repositório."""
    try:
        user_id = str(update.effective_user.id)

        # Consulta o MCP Server para obter as branches
        response = mcp_client.get_branches(user_id)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao listar branches: {response['error']}"
            )
            return

        if response.get("status") == "success":
            branches = response.get("branches", [])
            branches_str = "\n".join(branches)

            await update.message.reply_text(
                f"Branches do repositório:\n```\n{branches_str}\n```",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao listar branches.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao listar branches: {str(e)}")


async def checkout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muda para outra branch."""
    try:
        user_id = str(update.effective_user.id)

        if not context.args:
            await update.message.reply_text(
                "Por favor, especifique a branch.\nUso: /checkout <branch>"
            )
            return

        branch_name = context.args[0]

        # Solicita ao MCP Server para fazer checkout
        response = mcp_client.checkout_branch(user_id, branch_name, context.args)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao fazer checkout: {response['error']}"
            )
            return

        if response.get("status") == "success":
            await update.message.reply_text(f"Alterado para branch: {branch_name}")
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao fazer checkout.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao fazer checkout: {str(e)}")


async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Solicita ao Claude sugestões para modificar um arquivo."""
    try:
        user_id = str(update.effective_user.id)

        # Verifica se foram fornecidos argumentos suficientes
        if len(context.args) < 2:
            await update.message.reply_text(
                "Uso: /suggest <arquivo> <descrição da modificação desejada>"
            )
            return

        file_path = context.args[0]
        description = " ".join(context.args[1:])

        await update.message.reply_text(
            "Consultando Claude para sugestões de modificação. Aguarde um momento..."
        )

        # Solicita ao MCP Server para gerar sugestões
        response = mcp_client.suggest_modification(user_id, file_path, description)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao gerar sugestão: {response['error']}"
            )
            return

        if response.get("status") == "processing":
            # O processamento está sendo feito em segundo plano no MCP Server
            await update.message.reply_text(
                "A solicitação está sendo processada. Você receberá a sugestão em breve."
            )
        elif response.get("status") == "success":
            suggestion_id = response.get("suggestion_id", "")
            suggested_code = response.get("suggested_code", "")

            # Armazena a sugestão no contexto do usuário para uso posterior
            if "suggestions" not in context.user_data:
                context.user_data["suggestions"] = {}

            context.user_data["suggestions"][suggestion_id] = {
                "file_path": file_path,
                "description": description,
            }

            # Envia a sugestão para o usuário
            await update.message.reply_text(
                f"Sugestão #{suggestion_id} para '{file_path}':\n\n"
                f"```\n{suggested_code[:1000]}...\n```\n\n"
                f"(Mostrando apenas os primeiros 1000 caracteres)\n\n"
                f"Para aplicar: /apply {suggestion_id}\n"
                f"Para rejeitar: /reject {suggestion_id}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao gerar sugestão.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao gerar sugestão: {str(e)}")


async def apply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Aplica a sugestão proposta pelo Claude."""
    try:
        user_id = str(update.effective_user.id)

        # Verifica se foi fornecido um ID de sugestão
        if len(context.args) < 1:
            await update.message.reply_text("Uso: /apply <id_sugestão>")
            return

        # Obtém o ID da sugestão
        suggestion_id = context.args[0]

        # Solicita ao MCP Server para aplicar a sugestão
        response = mcp_client.apply_modification(user_id, suggestion_id)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao aplicar sugestão: {response['error']}"
            )
            return

        if response.get("status") == "success":
            file_path = response.get("file_path", "")

            await update.message.reply_text(
                f"Sugestão #{suggestion_id} aplicada com sucesso ao arquivo '{file_path}'.\n"
                f"Use /commit para confirmar as alterações."
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao aplicar sugestão.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao aplicar sugestão: {str(e)}")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rejeita a sugestão proposta pelo Claude."""
    try:
        user_id = str(update.effective_user.id)

        # Verifica se foi fornecido um ID de sugestão
        if len(context.args) < 1:
            await update.message.reply_text("Uso: /reject <id_sugestão>")
            return

        # Obtém o ID da sugestão
        suggestion_id = context.args[0]

        # Solicita ao MCP Server para rejeitar a sugestão
        response = mcp_client.reject_modification(user_id, suggestion_id)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao rejeitar sugestão: {response['error']}"
            )
            return

        if response.get("status") == "success":
            file_path = response.get("file_path", "")

            await update.message.reply_text(
                f"Sugestão #{suggestion_id} para '{file_path}' foi rejeitada."
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao rejeitar sugestão.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao rejeitar sugestão: {str(e)}")


async def commit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Realiza commit das alterações."""
    try:
        user_id = str(update.effective_user.id)

        # Verifica se foi fornecida uma mensagem de commit
        if len(context.args) < 1:
            await update.message.reply_text("Uso: /commit <mensagem>")
            return

        # Obtém a mensagem de commit
        commit_message = " ".join(context.args)

        # Solicita ao MCP Server para realizar o commit
        response = mcp_client.commit_changes(user_id, commit_message)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao realizar commit: {response['error']}"
            )
            return

        if response.get("status") == "success":
            await update.message.reply_text(
                f"Commit realizado com sucesso: '{commit_message}'.\n"
                f"Use /push para enviar as alterações para o GitHub."
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao realizar commit.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao realizar commit: {str(e)}")


async def push_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia as alterações para o GitHub."""
    try:
        user_id = str(update.effective_user.id)

        # Solicita ao MCP Server para realizar o push
        response = mcp_client.push_changes(user_id)

        if "error" in response:
            await update.message.reply_text(
                f"Erro ao enviar alterações: {response['error']}"
            )
            return

        if response.get("status") == "success":
            await update.message.reply_text(
                "Alterações enviadas com sucesso para o GitHub."
            )
        else:
            await update.message.reply_text(
                response.get("message", "Erro ao enviar alterações.")
            )
    except Exception as e:
        await update.message.reply_text(f"Erro ao enviar alterações: {str(e)}")


async def screenshot_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Captura e envia uma imagem da estrutura de diretórios."""
    try:
        user_id = str(update.effective_user.id)

        # Verifica se um repositório foi selecionado
        response = mcp_client.get_current_directory(user_id)

        if "error" in response or response.get("status") != "success":
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return

        # Determina a profundidade
        max_depth = 3  # Padrão
        if context.args:
            try:
                max_depth = int(context.args[0])
                # Limita a profundidade para evitar imagens muito grandes
                if max_depth > 5:
                    max_depth = 5
                    await update.message.reply_text(
                        "Profundidade máxima limitada a 5 para evitar excesso de dados."
                    )
            except ValueError:
                await update.message.reply_text(
                    "Profundidade inválida. Usando valor padrão (3)."
                )

        repo_path = response.get("repo_path", "")
        current_path = response.get("current_path", "")

        current_abs_dir = os.path.join(repo_path, current_path)

        # Informa ao usuário que a captura está sendo gerada
        await update.message.reply_text(
            "Gerando captura da estrutura de diretórios. Aguarde um momento..."
        )

        # Gera a captura
        screenshot_path = capture_directory_structure(current_abs_dir)

        if screenshot_path:
            # Envia a imagem pelo Telegram
            await update.message.reply_photo(
                photo=open(screenshot_path, "rb"),
                caption=f"Estrutura de diretórios: {os.path.basename(current_abs_dir) or response.get('repo_name', '')}",
            )

            # Remove o arquivo temporário
            os.unlink(screenshot_path)
        else:
            await update.message.reply_text(
                "Não foi possível gerar a captura da estrutura de diretórios."
            )

    except Exception as e:
        await update.message.reply_text(
            f"Erro ao capturar estrutura de diretórios: {str(e)}"
        )


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Captura e envia uma imagem do conteúdo de um arquivo."""
    try:
        user_id = str(update.effective_user.id)

        # Verifica se um repositório foi selecionado
        response = mcp_client.get_current_directory(user_id)

        if "error" in response or response.get("status") != "success":
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return

        if not context.args:
            await update.message.reply_text(
                "Por favor, especifique o arquivo.\nUso: /view <arquivo>"
            )
            return

        file_arg = " ".join(context.args)
        repo_path = response.get("repo_path", "")
        current_path = response.get("current_path", "")

        # Constrói o caminho do arquivo
        file_rel_path = os.path.normpath(os.path.join(current_path, file_arg))
        file_abs_path = os.path.join(repo_path, file_rel_path)

        # Verifica se o arquivo existe
        if not os.path.isfile(file_abs_path):
            await update.message.reply_text(f"Arquivo não encontrado: {file_rel_path}")
            return

        # Verifica o tamanho do arquivo
        file_size = os.path.getsize(file_abs_path)
        if file_size > 1000000:  # 1MB
            await update.message.reply_text(
                f"O arquivo é muito grande ({file_size / 1000000:.2f} MB). "
                f"Posso mostrar apenas arquivos menores que 1 MB."
            )
            return

        # Informa ao usuário que a captura está sendo gerada
        await update.message.reply_text(
            "Gerando captura do conteúdo do arquivo. Aguarde um momento..."
        )

        # Gera a captura
        screenshot_path = capture_file_content(file_abs_path)

        if screenshot_path:
            # Envia a imagem pelo Telegram
            await update.message.reply_photo(
                photo=open(screenshot_path, "rb"),
                caption=f"Conteúdo do arquivo: {file_rel_path}",
            )

            # Remove o arquivo temporário
            os.unlink(screenshot_path)
        else:
            await update.message.reply_text(
                "Não foi possível gerar a captura do conteúdo do arquivo."
            )

    except Exception as e:
        await update.message.reply_text(
            f"Erro ao capturar conteúdo do arquivo: {str(e)}"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa mensagens que não são comandos."""
    await update.message.reply_text(
        "Por favor, use comandos específicos para interagir comigo. "
        "Use /help para ver a lista de comandos disponíveis."
    )


def main() -> None:
    """Inicia o bot."""
    # Cria o aplicativo e passa o token do bot
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Adiciona handlers de navegação
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("repos", repos_command))
    application.add_handler(CommandHandler("select", select_command))
    application.add_handler(CommandHandler("ls", ls_command))
    application.add_handler(CommandHandler("cd", cd_command))
    application.add_handler(CommandHandler("pwd", pwd_command))
    application.add_handler(CommandHandler("tree", tree_command))
    application.add_handler(CommandHandler("cat", cat_command))

    # Adiciona handlers de Git
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("branch", branch_command))
    application.add_handler(CommandHandler("checkout", checkout_command))
    application.add_handler(CommandHandler("suggest", suggest_command))
    application.add_handler(CommandHandler("apply", apply_command))
    application.add_handler(CommandHandler("reject", reject_command))
    application.add_handler(CommandHandler("commit", commit_command))
    application.add_handler(CommandHandler("push", push_command))

    # Adiciona handler para mensagens não relacionadas a comandos
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Inicia o bot
    application.run_polling()


if __name__ == "__main__":
    main()
