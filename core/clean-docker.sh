#!/bin/bash

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${RED}🧹 Nettoyage complet de Docker pour Sterna${NC}\n"

# 1. Arrêter tous les containers
echo -e "${YELLOW}⏹  Arrêt de tous les containers...${NC}"
docker-compose down -v

# 2. Supprimer tous les containers du projet
echo -e "${YELLOW}🗑  Suppression des containers...${NC}"
docker-compose rm -f

# 3. Supprimer les images du projet
echo -e "${YELLOW}🗑  Suppression des images du projet...${NC}"
docker rmi -f $(docker images | grep "core-" | awk '{print $3}') 2>/dev/null || true
docker rmi -f $(docker images | grep "core_" | awk '{print $3}') 2>/dev/null || true

# 4. Nettoyer le cache Docker
echo -e "${YELLOW}🧹 Nettoyage du cache Docker...${NC}"
docker builder prune -f

# 5. Supprimer les volumes orphelins
echo -e "${YELLOW}🗑  Suppression des volumes orphelins...${NC}"
docker volume prune -f

echo -e "${GREEN}✅ Nettoyage terminé!${NC}\n"
echo -e "${BLUE}Pour reconstruire le projet, exécutez:${NC}"
echo -e "${GREEN}docker-compose build --no-cache${NC}"
echo -e "${GREEN}./start-dev.sh${NC}"