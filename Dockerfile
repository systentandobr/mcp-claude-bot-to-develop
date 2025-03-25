FROM python:3.10-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copia os arquivos de requisitos
COPY requirements.txt .

# Cria o ambiente virtual 
RUN python3 -m venv venv               
RUN source venv/bin/activate

RUN pip install --no-cache-dir -r requirements.txt

RUN pip uninstall -y langchain         
RUN pip install langchain==0.0.267

RUN pip uninstall -y pyautoguipip install -r requirements.txt

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código-fonte
COPY . .

# Cria volume para persistir os repositórios clonados
VOLUME /app/repos
