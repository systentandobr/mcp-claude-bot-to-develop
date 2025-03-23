import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from langchain.chat_models import ChatAnthropic
from git import Repo
import anthropic
from screenshot_utils import capture_directory_structure, capture_file_content
import tempfile

# Carrega variáveis de ambiente
load_dotenv()

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuração das chaves de API
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPOS_BASE_PATH = os.getenv('REPOS_BASE_PATH')  # Diretório raiz onde estão todos os repositórios

# Armazenamento do repositório atual de cada usuário
user_current_paths = {}

# Inicializa o cliente Claude
claude = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# O repositório será inicializado dinamicamente com base na seleção do usuário

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia mensagem quando o comando /start é emitido."""
    await update.message.reply_text(
        'Olá! Sou seu assistente de desenvolvimento. Posso te ajudar a modificar '
        'seu repositório GitHub usando o Claude. Use /help para ver os comandos disponíveis.'
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
        
        # Lista todos os diretórios no caminho base
        repos = [d for d in os.listdir(REPOS_BASE_PATH) 
                if os.path.isdir(os.path.join(REPOS_BASE_PATH, d)) and 
                os.path.isdir(os.path.join(REPOS_BASE_PATH, d, '.git'))]
        
        if not repos:
            await update.message.reply_text("Nenhum repositório Git encontrado no diretório base.")
            return
        
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
            await update.message.reply_text("Por favor, especifique o nome do repositório.\nUso: /select <nome_repo>")
            return
        
        repo_name = context.args[0]
        repo_path = os.path.join(REPOS_BASE_PATH, repo_name)
        
        if not os.path.isdir(repo_path):
            await update.message.reply_text(f"Repositório '{repo_name}' não encontrado. Use /repos para listar os disponíveis.")
            return
        
        if not os.path.isdir(os.path.join(repo_path, '.git')):
            await update.message.reply_text(f"O diretório '{repo_name}' não é um repositório Git válido.")
            return
        
        # Configura o caminho atual para o usuário
        user_current_paths[user_id] = {
            'repo_name': repo_name,
            'repo_path': repo_path,
            'current_dir': '' # Caminho relativo dentro do repo, inicialmente vazio (raiz)
        }
        
        await update.message.reply_text(
            f"Repositório '{repo_name}' selecionado com sucesso!\n"
            f"Use /ls para listar arquivos e diretórios ou /status para ver o status do Git."
        )
    except Exception as e:
        await update.message.reply_text(f"Erro ao selecionar repositório: {str(e)}")

async def ls_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista arquivos e pastas do diretório atual ou do caminho especificado."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        # Determina o caminho a ser listado
        path_arg = ' '.join(context.args) if context.args else ''
        
        # Construir o caminho completo
        user_info = user_current_paths[user_id]
        repo_path = user_info['repo_path']
        current_rel_dir = user_info['current_dir']
        
        # Combina o diretório atual com o argumento, se houver
        if path_arg:
            target_rel_path = os.path.normpath(os.path.join(current_rel_dir, path_arg))
        else:
            target_rel_path = current_rel_dir
        
        target_abs_path = os.path.join(repo_path, target_rel_path)
        
        # Verifica se o caminho existe e é um diretório
        if not os.path.isdir(target_abs_path):
            await update.message.reply_text(f"Caminho não encontrado ou não é um diretório: {target_rel_path}")
            return
        
        # Lista o conteúdo do diretório
        items = os.listdir(target_abs_path)
        
        # Separa diretórios e arquivos
        directories = []
        files = []
        
        for item in items:
            item_path = os.path.join(target_abs_path, item)
            if os.path.isdir(item_path):
                if item != '.git':  # Opcional: ocultar diretório .git
                    directories.append(f"📁 {item}/")
            else:
                files.append(f"📄 {item}")
        
        # Ordena as listas
        directories.sort()
        files.sort()
        
        # Cria a mensagem
        message = f"📂 Conteúdo de '{target_rel_path or '/'}':\n\n"
        
        if directories:
            message += "Diretórios:\n" + "\n".join(directories) + "\n\n"
        
        if files:
            message += "Arquivos:\n" + "\n".join(files)
        
        if not directories and not files:
            message += "Diretório vazio"
        
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Erro ao listar diretório: {str(e)}")

async def cd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Navega para o diretório especificado."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        if not context.args:
            await update.message.reply_text("Por favor, especifique o caminho.\nUso: /cd <caminho>")
            return
        
        path_arg = ' '.join(context.args)
        user_info = user_current_paths[user_id]
        repo_path = user_info['repo_path']
        current_rel_dir = user_info['current_dir']
        
        # Caso especial para voltar à raiz
        if path_arg == '/':
            user_current_paths[user_id]['current_dir'] = ''
            await update.message.reply_text("Navegado para a raiz do repositório.")
            return
        
        # Caso especial para voltar um nível
        if path_arg == '..':
            new_rel_dir = os.path.dirname(current_rel_dir)
            user_current_paths[user_id]['current_dir'] = new_rel_dir
            await update.message.reply_text(f"Navegado para '{new_rel_dir or '/'}'")
            return
        
        # Caso normal
        new_rel_dir = os.path.normpath(os.path.join(current_rel_dir, path_arg))
        new_abs_dir = os.path.join(repo_path, new_rel_dir)
        
        # Verifica se o caminho existe e é um diretório
        if not os.path.isdir(new_abs_dir):
            await update.message.reply_text(f"Caminho não encontrado ou não é um diretório: {new_rel_dir}")
            return
        
        # Atualiza o diretório atual
        user_current_paths[user_id]['current_dir'] = new_rel_dir
        
        await update.message.reply_text(f"Navegado para '{new_rel_dir or '/'}'")
    except Exception as e:
        await update.message.reply_text(f"Erro ao navegar para o diretório: {str(e)}")

async def pwd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o diretório atual."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        user_info = user_current_paths[user_id]
        repo_name = user_info['repo_name']
        current_dir = user_info['current_dir'] or '/'
        
        await update.message.reply_text(
            f"Repositório: {repo_name}\n"
            f"Diretório atual: {current_dir}"
        )
    except Exception as e:
        await update.message.reply_text(f"Erro ao mostrar diretório atual: {str(e)}")

def generate_tree(path, prefix="", max_depth=2, current_depth=0):
    """Gera uma representação em árvore de um diretório."""
    if current_depth > max_depth:
        return ""
    
    result = ""
    items = sorted(os.listdir(path))
    
    # Filtra itens para excluir o diretório .git
    items = [item for item in items if item != '.git']
    
    for i, item in enumerate(items):
        is_last = (i == len(items) - 1)
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

async def tree_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra a estrutura de diretórios."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        # Determina a profundidade
        max_depth = 2  # Padrão
        if context.args:
            try:
                max_depth = int(context.args[0])
                # Limita a profundidade para evitar mensagens muito grandes
                if max_depth > 4:
                    max_depth = 4
                    await update.message.reply_text("Profundidade máxima limitada a 4 para evitar excesso de dados.")
            except ValueError:
                await update.message.reply_text("Profundidade inválida. Usando valor padrão (2).")
        
        user_info = user_current_paths[user_id]
        repo_path = user_info['repo_path']
        current_rel_dir = user_info['current_dir']
        current_abs_dir = os.path.join(repo_path, current_rel_dir)
        
        # Gera a árvore
        tree_output = f"📂 {os.path.basename(current_abs_dir) or user_info['repo_name']}\n"
        tree_output += generate_tree(current_abs_dir, "", max_depth)
        
        # Verifica se a saída não é muito longa para o Telegram
        if len(tree_output) > 4000:
            tree_output = tree_output[:3900] + "\n\n... (saída truncada, use profundidade menor)"
        
        await update.message.reply_text(f"```\n{tree_output}\n```", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Erro ao gerar árvore: {str(e)}")

async def cat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o conteúdo de um arquivo."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        if not context.args:
            await update.message.reply_text("Por favor, especifique o arquivo.\nUso: /cat <arquivo>")
            return
        
        file_arg = ' '.join(context.args)
        user_info = user_current_paths[user_id]
        repo_path = user_info['repo_path']
        current_rel_dir = user_info['current_dir']
        
        # Constrói o caminho do arquivo
        file_rel_path = os.path.normpath(os.path.join(current_rel_dir, file_arg))
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
        
        # Determina o tipo de arquivo para formatação adequada
        _, file_ext = os.path.splitext(file_abs_path)
        
        # Lê o conteúdo do arquivo
        with open(file_abs_path, 'r', encoding='utf-8', errors='replace') as file:
            content = file.read()
        
        # Limita o tamanho do conteúdo
        if len(content) > 4000:
            content = content[:3900] + "\n\n... (conteúdo truncado)"
        
        # Envia o conteúdo formatado
        language = ''
        if file_ext in ['.py', '.js', '.java', '.c', '.cpp', '.cs', '.php', '.go', '.ts', '.html', '.css', '.json', '.xml']:
            language = file_ext[1:]  # Remove o ponto
        
        message = f"📄 {file_rel_path}:\n\n```{language}\n{content}\n```"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Erro ao mostrar arquivo: {str(e)}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verifica o status do repositório."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        repo_path = user_current_paths[user_id]['repo_path']
        repo = Repo(repo_path)
        
        # Atualiza o repositório
        origin = repo.remotes.origin
        origin.pull()
        
        # Obtém o status
        status = repo.git.status()
        
        await update.message.reply_text(f"Status do repositório:\n```\n{status}\n```", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Erro ao verificar status: {str(e)}")

async def branch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra as branches do repositório."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        repo_path = user_current_paths[user_id]['repo_path']
        repo = Repo(repo_path)
        
        # Lista as branches
        branches = repo.git.branch('-a').split('\n')
        
        await update.message.reply_text(f"Branches do repositório:\n```\n{chr(10).join(branches)}\n```", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Erro ao listar branches: {str(e)}")

async def checkout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muda para outra branch."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        if not context.args:
            await update.message.reply_text("Por favor, especifique a branch.\nUso: /checkout <branch>")
            return
        
        branch_name = context.args[0]
        repo_path = user_current_paths[user_id]['repo_path']
        repo = Repo(repo_path)
        
        # Executa o checkout
        repo.git.checkout(branch_name)
        
        await update.message.reply_text(f"Alterado para branch: {branch_name}")
    except Exception as e:
        await update.message.reply_text(f"Erro ao fazer checkout: {str(e)}")

async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Solicita ao Claude sugestões para modificar um arquivo."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        # Verifica se foram fornecidos argumentos suficientes
        if len(context.args) < 2:
            await update.message.reply_text(
                "Uso: /suggest <arquivo> <descrição da modificação desejada>"
            )
            return
        
        file_path = context.args[0]
        description = ' '.join(context.args[1:])
        
        user_info = user_current_paths[user_id]
        repo_path = user_info['repo_path']
        current_rel_dir = user_info['current_dir']
        
        # Constrói o caminho completo do arquivo
        file_rel_path = os.path.normpath(os.path.join(current_rel_dir, file_path))
        full_path = os.path.join(repo_path, file_rel_path)
        
        # Verifica se o arquivo existe
        if not os.path.exists(full_path):
            await update.message.reply_text(f"Arquivo não encontrado: {file_rel_path}")
            return
        
        # Lê o conteúdo do arquivo
        with open(full_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        await update.message.reply_text("Consultando Claude para sugestões de modificação. Aguarde um momento...")
        
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
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        suggested_code = response.content[0].text
        
        # Armazena a sugestão no contexto do usuário para uso posterior
        if 'suggestions' not in context.user_data:
            context.user_data['suggestions'] = {}
        
        suggestion_id = len(context.user_data['suggestions']) + 1
        context.user_data['suggestions'][suggestion_id] = {
            'file_path': file_path,
            'original': content,
            'suggested': suggested_code,
            'description': description
        }
        
        # Envia a sugestão para o usuário
        await update.message.reply_text(
            f"Sugestão #{suggestion_id} para '{file_path}':\n\n"
            f"```\n{suggested_code[:1000]}...\n```\n\n"
            f"(Mostrando apenas os primeiros 1000 caracteres)\n\n"
            f"Para aplicar: /apply {suggestion_id}\n"
            f"Para rejeitar: /reject {suggestion_id}"
        )
        
    except Exception as e:
        await update.message.reply_text(f"Erro ao gerar sugestão: {str(e)}")

async def apply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Aplica a sugestão proposta pelo Claude."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        # Verifica se foi fornecido um ID de sugestão
        if len(context.args) < 1:
            await update.message.reply_text("Uso: /apply <id_sugestão>")
            return
        
        # Obtém o ID da sugestão
        suggestion_id = int(context.args[0])
        
        # Verifica se a sugestão existe
        if 'suggestions' not in context.user_data or suggestion_id not in context.user_data['suggestions']:
            await update.message.reply_text(f"Sugestão #{suggestion_id} não encontrada.")
            return
        
        # Obtém os dados da sugestão
        suggestion = context.user_data['suggestions'][suggestion_id]
        file_path = suggestion['file_path']
        suggested_code = suggestion['suggested']
        
        repo_path = user_current_paths[user_id]['repo_path']
        
        # Aplica a sugestão
        full_path = os.path.join(repo_path, file_path)
        with open(full_path, 'w', encoding='utf-8') as file:
            file.write(suggested_code)
        
        await update.message.reply_text(
            f"Sugestão #{suggestion_id} aplicada com sucesso ao arquivo '{file_path}'.\n"
            f"Use /commit para confirmar as alterações."
        )
        
    except Exception as e:
        await update.message.reply_text(f"Erro ao aplicar sugestão: {str(e)}")

async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rejeita a sugestão proposta pelo Claude."""
    try:
        # Verifica se foi fornecido um ID de sugestão
        if len(context.args) < 1:
            await update.message.reply_text("Uso: /reject <id_sugestão>")
            return
        
        # Obtém o ID da sugestão
        suggestion_id = int(context.args[0])
        
        # Verifica se a sugestão existe
        if 'suggestions' not in context.user_data or suggestion_id not in context.user_data['suggestions']:
            await update.message.reply_text(f"Sugestão #{suggestion_id} não encontrada.")
            return
        
        # Remove a sugestão
        file_path = context.user_data['suggestions'][suggestion_id]['file_path']
        del context.user_data['suggestions'][suggestion_id]
        
        await update.message.reply_text(
            f"Sugestão #{suggestion_id} para '{file_path}' foi rejeitada."
        )
        
    except Exception as e:
        await update.message.reply_text(f"Erro ao rejeitar sugestão: {str(e)}")

async def commit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Realiza commit das alterações."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        # Verifica se foi fornecida uma mensagem de commit
        if len(context.args) < 1:
            await update.message.reply_text("Uso: /commit <mensagem>")
            return
        
        # Obtém a mensagem de commit
        commit_message = ' '.join(context.args)
        
        repo_path = user_current_paths[user_id]['repo_path']
        repo = Repo(repo_path)
        
        # Adiciona todas as alterações
        repo.git.add('--all')
        
        # Realiza o commit
        repo.git.commit('-m', commit_message)
        
        await update.message.reply_text(
            f"Commit realizado com sucesso: '{commit_message}'.\n"
            f"Use /push para enviar as alterações para o GitHub."
        )
        
    except Exception as e:
        await update.message.reply_text(f"Erro ao realizar commit: {str(e)}")

async def push_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia as alterações para o GitHub."""
    try:
        user_id = str(update.effective_user.id)
        
        # Verifica se um repositório foi selecionado
        if user_id not in user_current_paths:
            await update.message.reply_text(
                "Nenhum repositório selecionado. Use /repos para listar e /select para escolher um."
            )
            return
        
        repo_path = user_current_paths[user_id]['repo_path']
        repo = Repo(repo_path)
        
        # Envia as alterações para o GitHub
        origin = repo.remotes.origin
        origin.push()
        
        await update.message.reply_text("Alterações enviadas com sucesso para o GitHub.")
        
    except Exception as e:
        await update.message.reply_text(f"Erro ao enviar alterações: {str(e)}")

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Inicia o bot
    application.run_polling()

if __name__ == '__main__':
    main()
