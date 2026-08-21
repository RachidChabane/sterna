#!/bin/bash

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${RED}⏹  Arrêt de tous les services...${NC}"

# Arrêter Docker Compose
docker-compose down

# Tuer le processus frontend s'il existe
pkill -f "npm run dev" 2>/dev/null

echo -e "${GREEN}✓ Tous les services sont arrêtés${NC}"