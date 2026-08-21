#!/bin/bash

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Reconstruction complète du projet${NC}\n"

# 1. Arrêter tous les services
echo -e "${YELLOW}⏹  Arrêt de tous les services...${NC}"
docker-compose down -v

# 2. Supprimer les anciennes images
echo -e "${YELLOW}🗑  Suppression des anciennes images...${NC}"
docker-compose rm -f

# 3. Reconstruire toutes les images sans cache
echo -e "${GREEN}🔨 Reconstruction des images Docker...${NC}"
docker-compose build --no-cache

# 4. Démarrer les services
echo -e "${GREEN}🚀 Démarrage des services...${NC}"
./start-dev.sh

echo -e "${GREEN}✅ Reconstruction terminée!${NC}"