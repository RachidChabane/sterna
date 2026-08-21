#!/bin/bash

# Couleurs pour l'output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Sterna - Démarrage du projet${NC}\n"

# Fonction de nettoyage
cleanup() {
    echo -e "\n${YELLOW}⏹  Arrêt des services...${NC}"
    docker-compose down
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null
    fi
    exit 0
}

# Intercepter Ctrl+C
trap cleanup INT

# Vérifier Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker n'est pas installé${NC}"
    exit 1
fi

# Vérifier Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js n'est pas installé${NC}"
    exit 1
fi

# 1. Arrêter les services existants
echo -e "${YELLOW}🔄 Arrêt des services existants...${NC}"
docker-compose down

# 2. Reconstruire les images (force si --rebuild est passé)
if [[ "$1" == "--rebuild" ]]; then
    echo -e "${GREEN}🔨 Reconstruction complète des images...${NC}"
    docker-compose build --no-cache
else
    echo -e "${GREEN}🔨 Vérification des images...${NC}"
    docker-compose build
fi

# 3. Lancer les services backend
echo -e "${GREEN}📦 Démarrage des services backend...${NC}"
docker-compose up -d

# Vérifier si les conteneurs ont démarré
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Échec du démarrage des services Docker${NC}"
    echo -e "${YELLOW}Consultez les logs avec: docker-compose logs${NC}"
    exit 1
fi

# 4. Attendre que PostgreSQL soit prêt (avec timeout)
echo -e "${YELLOW}⏳ Attente de PostgreSQL...${NC}"
TIMEOUT=30
COUNTER=0
until docker-compose exec -T postgres pg_isready -U postgres &>/dev/null; do
    sleep 1
    COUNTER=$((COUNTER + 1))
    if [ $COUNTER -ge $TIMEOUT ]; then
        echo -e "${RED}❌ PostgreSQL n'a pas démarré après ${TIMEOUT} secondes${NC}"
        echo -e "${YELLOW}Vérifiez avec: docker-compose ps${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ PostgreSQL prêt${NC}"

# 4. Attendre que Redis soit prêt
echo -e "${YELLOW}⏳ Attente de Redis...${NC}"
until docker-compose exec -T redis redis-cli ping &>/dev/null; do
    sleep 1
done
echo -e "${GREEN}✓ Redis prêt${NC}"

# 5. Exécuter les migrations
echo -e "${GREEN}🔄 Application des migrations...${NC}"
docker-compose exec -T web python manage.py migrate

# 6. Vérifier/Créer le superuser (optionnel)
echo -e "${YELLOW}👤 Vérification du superuser...${NC}"
docker-compose exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    print('Créez un superuser avec: make createsuperuser')
else:
    print('✓ Superuser existe déjà')
"

# 7. Installer les dépendances frontend si nécessaire
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${GREEN}📦 Installation des dépendances frontend...${NC}"
    cd frontend && npm install && cd ..
else
    echo -e "${GREEN}✓ Dépendances frontend déjà installées${NC}"
fi

# 8. Lancer le frontend
echo -e "${GREEN}🎨 Démarrage du frontend...${NC}"
cd frontend && npm run dev &
FRONTEND_PID=$!
cd ..

# 9. Afficher les URLs
echo -e "\n${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✨ Projet démarré avec succès!${NC}\n"
echo -e "📍 ${BLUE}URLs disponibles:${NC}"
echo -e "   • Frontend:     ${GREEN}http://localhost:5173${NC}"
echo -e "   • Backend API:  ${GREEN}http://localhost:8000${NC}"
echo -e "   • Django Admin: ${GREEN}http://localhost:8000/admin${NC}"
echo -e "   • Flower:       ${GREEN}http://localhost:5555${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}\n"
echo -e "${YELLOW}Appuyez sur Ctrl+C pour arrêter tous les services${NC}\n"

# Afficher les logs du backend
echo -e "${BLUE}📋 Logs du backend:${NC}"
docker-compose logs -f --tail=50 web