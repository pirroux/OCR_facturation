# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 python:3.12-slim

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Répertoire de travail
WORKDIR /app

# Installation des dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie des fichiers requirements
COPY requirements.txt .

# Installation des dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

# Création du dossier pour les fichiers temporaires
RUN mkdir -p temp_files && chmod 777 temp_files

# Exposition du port
EXPOSE 8000

# Commande de démarrage pour FastAPI
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
