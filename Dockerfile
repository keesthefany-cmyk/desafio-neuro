FROM python:3.11-slim

# Diretório de trabalho
WORKDIR /app

# Variáveis de ambiente importantes
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7000

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências do Python
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia restante da aplicação
COPY . .

# Expor porta
EXPOSE 7000

# CMD padrão - pode ser sobrescrito no docker-compose
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7000"]
