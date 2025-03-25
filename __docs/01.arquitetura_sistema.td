flowchart TD
    A[Usuário] -->|Envia mensagens| B[Bot Telegram]
    B -->|Processa comandos| C[Servidor MCP]
    C -->|Consulta/Modifica| D[Repositório GitHub]
    C -->|Envia prompt| E[API Claude]
    E -->|Retorna sugestões| C
    C -->|Envia modificações| B
    B -->|Mostra sugestões| A
    A -->|Aprova/Rejeita| B
    B -->|Comunica decisão| C
    C -->|Aplica mudanças| D
    C -->|Inicia CI/CD| F[GitHub Actions]