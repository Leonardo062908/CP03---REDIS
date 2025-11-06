# Redis Event App

Este projeto foi desenvolvido como parte do Checkpoint 3 (CP3) do segundo semestre da FIAP, demonstrando a implementação de um sistema de gestão de eventos usando Redis para cache, filas e pub/sub.

## 🎯 Objetivo

Desenvolver uma aplicação de gestão de eventos ao vivo que precisa responder rapidamente a usuários, mesmo com grande volume de acessos. O Redis é utilizado como mecanismo intermediador de dados temporários, mensagens e notificações.

## 🏗 Arquitetura

O projeto está dividido em três partes principais:

### Parte 1 - Cache de Dados de Evento

- Cache com TTL de 60 segundos
- Chaves no padrão `event:<event_id>`
- Operações GET e SETEX do Redis
- Fonte simulada em memória

### Parte 2 - Fila de Notificações

- Lista Redis como fila (`notificacao:fila`)
- LPUSH para inserção
- BRPOP para consumo bloqueante
- Processamento FIFO de notificações

### Parte 3 - Pub/Sub de Eventos

- Canal `eventos:atualizacoes`
- Publicação de atualizações de eventos
- Subscrição em tempo real
- Mensagens com event_id e título

## 🚀 Como Executar

### Pré-requisitos

#### Python

- Python 3.10 ou superior
- pip (gerenciador de pacotes Python)
- Conhecimento básico de comandos no terminal

#### Docker e Redis

- Docker Desktop (Windows/Mac) ou Docker Engine (Linux)
- Porta 6379 disponível para o Redis
- Não é necessário instalar o Redis separadamente, usaremos via Docker

#### Git e Ferramentas

- Git instalado e configurado
- Terminal (PowerShell no Windows, bash/zsh no Linux/Mac)

#### Verificando os Pré-requisitos

1. Verifique a versão do Python:

```bash
python --version  # Deve mostrar 3.10 ou superior
```

2. Verifique a instalação do Docker:

```bash
docker --version
```

3. Verifique se a porta 6379 está livre:

```bash
# Windows (PowerShell)
netstat -an | findstr "6379"

# Linux/Mac
netstat -an | grep "6379"
```

4. Verifique a instalação do Git:

```bash
git --version
```

#### Possíveis Problemas e Soluções

1. **Erro ao criar ambiente virtual**

   ```
   Error: [WinError 2] O sistema não pode encontrar o arquivo especificado
   ```

   Solução: Instale o módulo venv

   ```bash
   python -m pip install --user virtualenv
   ```

2. **Erro ao conectar no Redis**

   ```
   ConnectionError: Error -2 connecting to redis:6379. Name or service not known.
   ```

   Soluções:

   - Verifique se o container Redis está rodando
   - Verifique se não há outro serviço usando a porta 6379
   - Tente reiniciar o container Docker

3. **Erro de permissão no Docker**
   ```
   Permission denied while trying to connect...
   ```
   Solução:
   - Windows: Execute o PowerShell como administrador
   - Linux: Adicione seu usuário ao grupo docker
     ```bash
     sudo usermod -aG docker $USER
     ```

### Instalação

1. Clone o repositório:

```bash
git clone https://github.com/Leonardo062908/CP03---REDIS.git
cd CP03---REDIS
```

2. Crie e ative um ambiente virtual Python:

```powershell
# Windows (PowerShell)
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Inicie o Redis via Docker:

```bash
docker run --name redis-local -p 6379:6379 -d redis
```

Para verificar se o Redis está rodando:

```bash
# Via Docker CLI
docker ps

# Ou verifique no Docker Desktop na seção "Containers"
```

#### Gerenciando o Container Redis

- **Parar o container:**

  ```bash
  docker stop redis-local
  ```

- **Iniciar o container novamente:**

  ```bash
  docker start redis-local
  ```

- **Remover o container (caso necessário):**

  ```bash
  docker rm -f redis-local
  ```

- **Verificar logs do Redis:**

  ```bash
  docker logs redis-local
  ```

- **Acessar o Redis CLI:**
  ```bash
  docker exec -it redis-local redis-cli
  ```

## 📝 Como Testar

### Parte 1 - Cache

```bash
# Primeiro acesso (MISS)
python main.py cache get --id 101

# Segundo acesso (HIT)
python main.py cache get --id 101

# Verificar TTL restante
python main.py cache get --id 101 --show-ttl

# Teste com TTL customizado
python main.py cache get --id 101 --ttl 10

# Limpar cache
python main.py cache del --id 101
```

### Parte 2 - Fila de Notificações

Terminal A (Worker):

```bash
python main.py notify worker
```

Terminal B (Produtor):

```bash
# Enviar notificação individual
python main.py notify enqueue --user "Leo" --message "Ingressos liberados"

# Enviar lote de notificações
python main.py notify enqueue-batch --file msgs.jsonl
```

### Parte 3 - Pub/Sub

Terminal A (Subscriber):

```bash
python main.py events subscribe
```

Terminal B (Publisher):

```bash
# Publicar eventos
python main.py events publish --id 101
python main.py events publish --id 102
python main.py events publish --id 103

# Testar erro (ID inexistente)
python main.py events publish --id 999
```

## 🔍 Recursos e Diferenciais

1. **Robustez**

   - Tratamento completo de erros
   - Recuperação de falhas de conexão
   - Validação de dados

2. **Usabilidade**

   - Interface CLI intuitiva
   - Comandos bem documentados
   - Saídas JSON formatadas
   - Logs informativos

3. **Flexibilidade**

   - TTL customizável para cache
   - Suporte a processamento em lote
   - Configuração via variáveis de ambiente

4. **Monitoramento**
   - Logs detalhados
   - Contagem de receivers no pub/sub
   - Visualização de TTL do cache

## 🛠 Variáveis de Ambiente

- `REDIS_URL`: URL de conexão com o Redis (padrão: `redis://localhost:6379/0`)

## 📊 Estrutura de Dados

### Eventos Simulados

```python
{
    "101": {
        "event_id": "101",
        "titulo": "Tech Summit",
        "inicio": "2025-11-20T10:00:00Z",
        "local": "Pavilhão 1"
    }
    # ... outros eventos
}
```

### Formato de Notificações

```json
{
  "user": "string",
  "message": "string",
  "ts": "ISO-8601 timestamp"
}
```

### Formato de Mensagens Pub/Sub

```json
{
  "event_id": "string",
  "titulo": "string",
  "ts": "ISO-8601 timestamp"
}
```

## 🤝 Contribuindo

Este projeto foi desenvolvido para fins educacionais como parte do CP3 da FIAP. Sugestões e melhorias são bem-vindas através de issues e pull requests.

## ⚠️ Observações

- O projeto usa uma fonte simulada em memória para demonstração
- Para ambientes de produção, considere:
  - Implementar uma fonte de dados persistente
  - Adicionar autenticação/autorização
  - Configurar backup do Redis
  - Implementar rate limiting

## 📄 Licença

Este projeto é para fins educacionais e faz parte da entrega do CP3 da FIAP.

## 👥 Autores

- Leonardo Matheus Teixeira
- Leonardo Menezes Parpinelli Ribas
- Gabriel Marques de Lima Sousa
- Cauã Marcelo da Silva Machado
