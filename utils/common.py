import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def read_env_file() -> List[str]:
    """
    Lê o conteúdo do arquivo .env e retorna como uma lista de linhas.

    Returns:
        List[str]: Lista contendo cada linha do arquivo .env
    """
    env_content = []
    try:
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                env_content = f.readlines()
        else:
            logger.warning("Arquivo .env não encontrado.")
    except Exception as e:
        logger.error(f"Erro ao ler arquivo .env: {str(e)}")

    return env_content


def write_env_file(env_content: List[str]) -> bool:
    """
    Escreve o conteúdo fornecido no arquivo .env.

    Args:
        env_content (List[str]): Lista de linhas para escrever no arquivo .env

    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário
    """
    try:
        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(env_content)
        return True
    except Exception as e:
        logger.error(f"Erro ao escrever arquivo .env: {str(e)}")
        return False


def get_env_var(var_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Obtém o valor de uma variável de ambiente, com fallback para o arquivo .env
    se a variável não estiver definida no ambiente.

    Args:
        var_name (str): Nome da variável de ambiente
        default (Optional[str], optional): Valor padrão caso a variável não seja encontrada.
                                           Defaults to None.

    Returns:
        Optional[str]: Valor da variável de ambiente ou None se não encontrada
    """
    # Primeiro tenta obter do ambiente
    value = os.getenv(var_name)

    # Se não encontrou, procura no arquivo .env
    if value is None:
        env_content = read_env_file()
        for line in env_content:
            if line.strip().startswith(f"{var_name}="):
                value = line.strip().split("=", 1)[1].strip()
                # Remove aspas, se presentes
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                break

    # Se ainda não encontrou, retorna o valor padrão
    return value if value is not None else default


def update_env_var(var_name: str, value: str) -> bool:
    """
    Atualiza ou adiciona uma variável no arquivo .env.

    Args:
        var_name (str): Nome da variável
        value (str): Valor a ser definido

    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário
    """
    try:
        env_content = read_env_file()

        # Procura a linha com a variável
        var_line_found = False
        for i, line in enumerate(env_content):
            if line.strip().startswith(f"{var_name}="):
                env_content[i] = f"{var_name}={value}\n"
                var_line_found = True
                break

        # Se não encontrou, adiciona no final
        if not var_line_found:
            env_content.append(f"{var_name}={value}\n")

        # Escreve de volta no arquivo
        return write_env_file(env_content)

    except Exception as e:
        logger.error(f"Erro ao atualizar variável no arquivo .env: {str(e)}")
        return False


def load_all_env_vars() -> Dict[str, str]:
    """
    Carrega todas as variáveis do arquivo .env e retorna como um dicionário.

    Returns:
        Dict[str, str]: Dicionário com todas as variáveis do arquivo .env
    """
    env_vars = {}
    env_content = read_env_file()

    for line in env_content:
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Remove aspas, se presentes
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]

                env_vars[key] = value
            except ValueError:
                # Ignora linhas que não têm o formato key=value
                continue

    return env_vars


def get_connection_config() -> Dict[str, Any]:
    """
    Obtém configurações de conexão comuns para os componentes do sistema.

    Returns:
        Dict[str, Any]: Dicionário com as configurações de conexão
    """
    return {
        "telegram_token": get_env_var("TELEGRAM_TOKEN"),
        "claude_api_key": get_env_var("CLAUDE_API_KEY"),
        "github_token": get_env_var("GITHUB_TOKEN"),
        "repos_base_path": get_env_var("REPOS_BASE_PATH"),
        "mcp_host": get_env_var("MCP_HOST", "localhost"),
        "mcp_port": get_env_var("MCP_PORT", "8000"),
        "mcp_api_key": get_env_var("MCP_API_KEY"),
        "encryption_key": get_env_var("ENCRYPTION_KEY"),
    }


def get_repo_info() -> Dict[str, Any]:
    """
    Obtém informações relacionadas aos repositórios e configurações Git.

    Returns:
        Dict[str, Any]: Dicionário com informações dos repositórios
    """
    return {
        "repos_base_path": get_env_var("REPOS_BASE_PATH"),
        "github_token": get_env_var("GITHUB_TOKEN"),
        "github_username": get_env_var("GITHUB_USERNAME"),
        "github_email": get_env_var("GITHUB_EMAIL", "bot@example.com"),
    }


def get_security_config() -> Dict[str, Any]:
    """
    Obtém configurações relacionadas à segurança.

    Returns:
        Dict[str, Any]: Dicionário com configurações de segurança
    """
    return {
        "encryption_key": get_env_var("ENCRYPTION_KEY"),
        "mcp_api_key": get_env_var("MCP_API_KEY"),
        "authorized_users": get_env_var("AUTHORIZED_USERS", "").split(","),
        "admin_users": get_env_var("ADMIN_USER", "").split(","),
    }
