#!/bin/bash

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Executando verificações de código...${NC}"

# Verifica formatação com Black
echo -e "${BLUE}Verificando formatação com Black...${NC}"
black --check .
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Formatação OK${NC}"
else
    echo -e "${YELLOW}⚠ Arquivos precisam ser reformatados. Executando black...${NC}"
    black .
    echo -e "${GREEN}✓ Formatação aplicada${NC}"
fi

# Verifica ordenação de imports com isort
echo -e "${BLUE}Verificando ordenação de imports com isort...${NC}"
isort --check --profile black .
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Ordenação de imports OK${NC}"
else
    echo -e "${YELLOW}⚠ Imports precisam ser reordenados. Executando isort...${NC}"
    isort --profile black .
    echo -e "${GREEN}✓ Ordenação de imports aplicada${NC}"
fi

# Executa flake8
echo -e "${BLUE}Executando flake8...${NC}"
flake8 .
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Flake8 OK${NC}"
else
    echo -e "${RED}✗ Flake8 encontrou problemas${NC}"
fi

# Executa pylint
echo -e "${BLUE}Executando pylint...${NC}"
pylint --disable=C0111,R0903,C0103 $(git ls-files '*.py')
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Pylint OK${NC}"
else
    echo -e "${RED}✗ Pylint encontrou problemas${NC}"
fi

# Executa testes
echo -e "${BLUE}Executando testes...${NC}"
pytest --cov=.
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Testes OK${NC}"
else
    echo -e "${RED}✗ Testes falharam${NC}"
fi

echo -e "${BLUE}Verificações concluídas.${NC}"