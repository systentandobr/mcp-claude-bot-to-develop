#!/bin/bash

# Script para configurar o ambiente de CI/CD e testes
# Cria diretórios necessários e configura o ambiente GitHub Actions

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Configurando ambiente de CI/CD para o Telegram Dev Bot...${NC}"

# Verifica se está dentro do diretório do projeto
if [ ! -f "README.md" ] || [ ! -d "security" ]; then
    echo -e "${RED}Erro: Execute este script dentro do diretório principal do projeto.${NC}"
    exit 1
fi

# Cria estrutura de diretórios
echo -e "${GREEN}Criando estrutura de diretórios para testes...${NC}"

mkdir -p tests
mkdir -p .github/workflows
mkdir -p test_repos # Para testes que precisam de um diretório de repositórios

# Cria diretório de testes se ainda não existir
if [ ! -d "tests" ]; then
    mkdir -p tests
    echo -e "${GREEN}Diretório de testes criado.${NC}"
else
    echo -e "${YELLOW}Diretório de testes já existe.${NC}"
fi

# Cria arquivo __init__.py para o pacote de testes
touch tests/__init__.py

# Copia os arquivos de testes
echo -e "${GREEN}Copiando arquivos de testes...${NC}"

# Verifica e copia os arquivos de teste
if [ -f "tests/test_user_auth.py" ]; then
    echo -e "${YELLOW}Arquivo test_user_auth.py já existe, pulando...${NC}"
else
    cat > tests/test_user_auth.py << 'EOL'
import os
import pytest
import sys
import tempfile
from unittest.mock import patch, MagicMock

# Adiciona o diretório raiz ao path para importação
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importa o módulo para teste
from security.user_auth import UserAuth

class TestUserAuth:
    @pytest.fixture
    def mock_env(self):
        with patch.dict(os.environ, {
            "AUTHORIZED_USERS": "123456,789012",
            "ADMIN_USER": "123456"
        }):
            yield

    def test_load_authorized_users(self, mock_env):
        auth = UserAuth()
        assert "123456" in auth.authorized_users
        assert "789012" in auth.authorized_users
        assert "123456" in auth.admin_users
        assert "789012" not in auth.admin_users

    def test_is_authorized(self, mock_env):
        auth = UserAuth()
        assert auth.is_authorized("123456") is True
        assert auth.is_authorized("789012") is True
        assert auth.is_authorized("999999") is False

    def test_is_admin(self, mock_env):
        auth = UserAuth()
        assert auth.is_admin("123456") is True
        assert auth.is_admin("789012") is False
        assert auth.is_admin("999999") is False

    def test_generate_invite_token(self, mock_env):
        auth = UserAuth()
        # Admin pode gerar token
        token = auth.generate_invite_token("123456")
        assert token is not None
        assert len(token) > 0
        assert token in auth.user_tokens

        # Não-admin não pode gerar token
        token = auth.generate_invite_token("789012")
        assert token is None

    def test_redeem_invite_token(self, mock_env):
        auth = UserAuth()
        
        # Gera um token para teste
        token = auth.generate_invite_token("123456")
        
        # Resgata o token com um novo usuário
        result = auth.redeem_invite_token(token, "555555")
        assert result is True
        assert "555555" in auth.authorized_users
        
        # Verifica que o token foi removido
        assert token not in auth.user_tokens
        
        # Tenta resgatar um token inválido
        result = auth.redeem_invite_token("invalid_token", "666666")
        assert result is False
        assert "666666" not in auth.authorized_users
EOL
    echo -e "${GREEN}Arquivo test_user_auth.py criado.${NC}"
fi

if [ -f "tests/test_encryption.py" ]; then
    echo -e "${YELLOW}Arquivo test_encryption.py já existe, pulando...${NC}"
else
    cat > tests/test_encryption.py << 'EOL'
import os
import pytest
import sys
import tempfile
from unittest.mock import patch, MagicMock
import base64

# Adiciona o diretório raiz ao path para importação
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importa o módulo para teste - com mock para evitar dependência de ambiente
with patch.dict(os.environ, {"ENCRYPTION_KEY": base64.urlsafe_b64encode(b'A' * 32).decode()}):
    from security.encryption import EncryptionManager

class TestEncryptionManager:
    @pytest.fixture
    def encryption_manager(self):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": base64.urlsafe_b64encode(b'A' * 32).decode()}):
            manager = EncryptionManager()
            return manager

    def test_encrypt_decrypt_text(self, encryption_manager):
        # Texto original
        original_text = "Texto confidencial para teste"
        
        # Criptografa o texto
        encrypted_text = encryption_manager.encrypt_text(original_text)
        assert encrypted_text is not None
        assert encrypted_text != original_text
        
        # Descriptografa o texto
        decrypted_text = encryption_manager.decrypt_text(encrypted_text)
        assert decrypted_text == original_text
EOL
    echo -e "${GREEN}Arquivo test_encryption.py criado.${NC}"
fi

# Cria os arquivos de configuração
echo -e "${GREEN}Criando arquivos de configuração para testes...${NC}"

# pytest.ini
if [ -f "pytest.ini" ]; then
    echo -e "${YELLOW}Arquivo pytest.ini já existe, pulando...${NC}"
else
    cat > pytest.ini << 'EOL'
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --cov=. --cov-report=term --cov-report=xml --junitxml=test-results.xml

# Ignore coverage for test files
omit =
    tests/*
    setup.py
EOL
    echo -e "${GREEN}Arquivo pytest.ini criado.${NC}"
fi

# .flake8
if [ -f ".flake8" ]; then
    echo -e "${YELLOW}Arquivo .flake8 já existe, pulando...${NC}"
else
    cat > .flake8 << 'EOL'
[flake8]
max-line-length = 100
exclude = .git,__pycache__,build,dist,venv,.venv
ignore = E203, W503
per-file-ignores =
    __init__.py:F401
    tests/*:E501
EOL
    echo -e "${GREEN}Arquivo .flake8 criado.${NC}"
fi

# Configurando GitHub Actions
echo -e "${GREEN}Configurando GitHub Actions...${NC}"

# Workflow CI
if [ -f ".github/workflows/ci.yml" ]; then
    echo -e "${YELLOW}Arquivo ci.yml já existe, pulando...${NC}"
else
    mkdir -p .github/workflows
    cat > .github/workflows/ci.yml << 'EOL'
name: CI Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
  workflow_dispatch:  # Permite execução manual

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install flake8 pylint black isort
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      
      - name: Run black
        run: black --check .
      
      - name: Run isort
        run: isort --check --profile black .
      
      - name: Run flake8
        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
      
      - name: Run pylint
        run: pylint --disable=C0111,R0903,C0103 $(git ls-files '*.py')

  security-check:
    name: Security Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install bandit safety
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      
      - name: Run bandit
        run: bandit -r . -x ./tests
      
      - name: Run safety check
        run: safety check

  test:
    name: Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      
      - name: Create .env file for testing
        run: |
          echo "TELEGRAM_TOKEN=dummy_token" > .env
          echo "CLAUDE_API_KEY=dummy_api_key" >> .env
          echo "GITHUB_TOKEN=dummy_github_token" >> .env
          echo "REPOS_BASE_PATH=./test_repos" >> .env
          echo "MCP_API_KEY=dummy_mcp_key" >> .env
          echo "ENCRYPTION_KEY=dummy_encryption_key" >> .env
          echo "AUTHORIZED_USERS=123456789" >> .env
          echo "ADMIN_USER=123456789" >> .env
          mkdir -p test_repos
      
      - name: Run tests
        run: pytest --cov=. --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: true

  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: [lint, security-check, test]
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Build Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: false
          load: true
          tags: telegram-dev-bot:test
          cache-from: type=gha
          cache-to: type=gha,mode=max
EOL
    echo -e "${GREEN}Arquivo ci.yml criado.${NC}"
fi

# Workflow Deploy
if [ -f ".github/workflows/deploy.yml" ]; then
    echo -e "${YELLOW}Arquivo deploy.yml já existe, pulando...${NC}"
else
    mkdir -p .github/workflows
    cat > .github/workflows/deploy.yml << 'EOL'
name: Deploy to Production

on:
  release:
    types: [published]
  workflow_dispatch:  # Permite execução manual

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      
      - name: Create .env file for testing
        run: |
          echo "TELEGRAM_TOKEN=dummy_token" > .env
          echo "CLAUDE_API_KEY=dummy_api_key" >> .env
          echo "GITHUB_TOKEN=dummy_github_token" >> .env
          echo "REPOS_BASE_PATH=./test_repos" >> .env
          echo "MCP_API_KEY=dummy_mcp_key" >> .env
          echo "ENCRYPTION_KEY=dummy_encryption_key" >> .env
          echo "AUTHORIZED_USERS=123456789" >> .env
          echo "ADMIN_USER=123456789" >> .env
          mkdir -p test_repos
      
      - name: Run tests
        run: pytest

  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to DockerHub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/telegram-dev-bot:latest,${{ secrets.DOCKERHUB_USERNAME }}/telegram-dev-bot:${{ github.ref_name }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    name: Deploy to Server
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Install SSH key
        uses: shimataro/ssh-key-action@v2
        with:
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          known_hosts: ${{ secrets.SSH_KNOWN_HOSTS }}
      
      - name: Deploy using SSH
        run: |
          ssh ${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }} << 'EOF'
            cd /opt/telegram-dev-bot
            docker-compose pull
            docker-compose down
            docker-compose up -d
            docker image prune -f
          EOF
EOL
    echo -e "${GREEN}Arquivo deploy.yml criado.${NC}"
fi

# Cria arquivo .gitignore ou adiciona entradas específicas para testes
if [ -f ".gitignore" ]; then
    # Verifica se já contém as entradas necessárias
    if ! grep -q "\.coverage" .gitignore || ! grep -q "coverage\.xml" .gitignore; then
        echo -e "${GREEN}Adicionando entradas de teste ao .gitignore...${NC}"
        cat >> .gitignore << 'EOL'

# Test files
.coverage
coverage.xml
test-results.xml
.pytest_cache/
__pycache__/
*.pyc
EOL
    else
        echo -e "${YELLOW}Arquivo .gitignore já contém entradas para testes.${NC}"
    fi
else
    echo -e "${GREEN}Criando arquivo .gitignore...${NC}"
    cat > .gitignore << 'EOL'
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Environment
.env
.venv
env/
venv/
ENV/

# Logs
logs/
*.log

# Test files
.coverage
coverage.xml
test-results.xml
.pytest_cache/

# Docker
.dockerignore

# Editor files
.idea/
.vscode/
*.swp
*.swo

# Repositories directory
repos/
test_repos/
EOL
    echo -e "${GREEN}Arquivo .gitignore criado.${NC}"
fi

# Instala dependências de desenvolvimento
echo -e "${BLUE}Deseja instalar as dependências de desenvolvimento para testes? (y/n)${NC}"
read install_deps

if [ "$install_deps" = "y" ] || [ "$install_deps" = "Y" ]; then
    echo -e "${GREEN}Instalando dependências de desenvolvimento...${NC}"
    pip install pytest pytest-cov black isort flake8 pylint bandit safety
    echo -e "${GREEN}Dependências instaladas com sucesso!${NC}"
fi

echo -e "${GREEN}Configuração de CI/CD e testes concluída com sucesso!${NC}"
echo -e "${BLUE}Para executar os testes localmente:${NC}"
echo -e "  pytest --cov=."
echo -e "${BLUE}Para formatar o código:${NC}"
echo -e "  black ."
echo -e "  isort ."
echo -e "${BLUE}Para verificar o código:${NC}"
echo -e "  flake8 ."
echo -e "  pylint \$(git ls-files '*.py')"
echo -e "${BLUE}Para verificar vulnerabilidades:${NC}"
echo -e "  bandit -r . -x ./tests"
echo -e "  safety check"
echo -e "\n${BLUE}Os workflows do GitHub Actions estão configurados em .github/workflows/${NC}"
