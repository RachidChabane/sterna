"""
Configuration centralisée pour Consigliere AI Advisor.

Ce module centralise toutes les constantes numériques et paramètres configurables
du module Consigliere pour faciliter la maintenance et les modifications.
"""


# =============================================================================
# AI Analysis Configuration
# =============================================================================

class AIAnalysisConfig:
    """Configuration pour l'analyse AI (ai_analyzer.py)"""

    # Paramètres de génération AI
    TEMPERATURE = 0.3  # Température pour génération structurée (plus bas = plus déterministe)
    MAX_TOKENS = 30000  # Tokens maximum pour la réponse AI (ajusté dynamiquement selon le modèle)

    # Limites de conversation
    MAX_MESSAGES_PER_CHAT = 200  # Messages max inclus par chat dans l'analyse
    MAX_MESSAGE_LENGTH = 10000  # Longueur max d'un message en caractères (tronqué après)

    # Modèles disponibles
    AVAILABLE_MODELS_LIMIT = 30  # Nombre max de modèles dans la liste de recommandations


# =============================================================================
# Chat Configuration
# =============================================================================

class ChatConfig:
    """Configuration pour le chat Consigliere (chat_handler.py)"""

    TEMPERATURE = 0.7  # Température par défaut pour chat (plus créatif que l'analyse)
    MAX_TOKENS = 2000  # Tokens maximum par défaut pour réponses chat


# =============================================================================
# Model Parameters Defaults
# =============================================================================

class ModelParametersDefaults:
    """
    Valeurs par défaut pour tous les paramètres de modèle LLM.

    ⚠️ SYNCHRONISATION BACKEND/FRONTEND:
    Ces valeurs doivent être synchronisées avec le frontend:
    /frontend/src/config/modelParameters.ts -> MODEL_PARAMETERS_DEFAULTS

    Toute modification ici doit être répercutée dans le frontend et vice versa.
    """

    # Paramètres de génération principaux
    TEMPERATURE = 0.7  # Contrôle la créativité (0.0 = déterministe, 1.0+ = créatif)
    MAX_TOKENS = 16384  # UI default — backend resolves to model's actual max_completion_tokens

    # Paramètres de sampling
    TOP_P = 1.0  # Nucleus sampling (0.0-1.0)
    TOP_K = 0  # Top-K sampling (0 = désactivé)

    # Paramètres de pénalité
    FREQUENCY_PENALTY = 0.0  # Pénalise la répétition de tokens fréquents (-2.0 à 2.0)
    PRESENCE_PENALTY = 0.0  # Pénalise la répétition de tokens présents (-2.0 à 2.0)
    REPETITION_PENALTY = 1.0  # Pénalité de répétition (1.0 = pas de pénalité)

    # Paramètres avancés
    MIN_P = 0.0  # Minimum probability threshold (0.0-1.0)
    TOP_A = 0.0  # Top-A sampling (0.0 = désactivé)


# =============================================================================
# Context Building Configuration
# =============================================================================

class ContextConfig:
    """Configuration pour construction du contexte (context_builder.py)"""

    MAX_MESSAGES_PER_CHAT = 10  # Messages max pour contexte (moins que pour analyse complète)
    MAX_MESSAGE_LENGTH = 500  # Longueur max message pour contexte (plus court pour économiser tokens)


# =============================================================================
# Scoring & Recommendation Configuration
# =============================================================================

class ScoringConfig:
    """Configuration pour le système de scoring (recommender.py)"""

    # Poids des critères de scoring (doivent sommer à 1.0)
    COST_WEIGHT = 0.4  # Poids du coût dans le score final
    QUALITY_WEIGHT = 0.3  # Poids de la qualité dans le score final
    SPEED_WEIGHT = 0.2  # Poids de la vitesse dans le score final
    CONTEXT_WEIGHT = 0.1  # Poids de la longueur de contexte dans le score final

    # Scores de qualité par tier (0.0 à 1.0)
    QUALITY_SCORES = {
        "premium": 1.0,  # Meilleurs modèles (GPT-4, Claude Opus, etc.)
        "high": 0.8,     # Très bons modèles (GPT-3.5 Turbo, Claude Sonnet, etc.)
        "medium": 0.6,   # Bons modèles (Gemma, Llama 3, etc.)
        "budget": 0.4,   # Modèles économiques
    }

    # Scores de vitesse par tier (0.0 à 1.0)
    SPEED_SCORES = {
        "very_fast": 1.0,  # < 1s latence
        "fast": 0.8,       # 1-3s latence
        "moderate": 0.6,   # 3-7s latence
        "slow": 0.4,       # > 7s latence
    }

    # Normalisation du contexte
    CONTEXT_NORMALIZATION_THRESHOLD = 100000  # Tokens - seuil pour normaliser le score de contexte

    # Multiplicateurs de préférence
    BUDGET_PREFERENCE_MULTIPLIER = 1.2  # Boost pour modèles budget/premium selon préférence utilisateur

    # Seuil de contexte large
    LARGE_CONTEXT_THRESHOLD = 100000  # Tokens - seuil pour considérer un contexte comme "large"

    # Token cost calculation
    TOKEN_PRICE_DIVISOR = 1000  # Prices are per 1K tokens
    DEFAULT_FALLBACK_TOKENS = 1000  # Default token count when no data available

    # Token distribution ratios (for fallback estimation)
    PROMPT_TOKEN_RATIO = 0.67  # 67% prompt tokens (2:1 prompt to completion ratio)
    COMPLETION_TOKEN_RATIO = 0.33  # 33% completion tokens

    # Tier comparison scores (for calculating deltas)
    QUALITY_TIER_SCORES = {
        "premium": 4,
        "high": 3,
        "medium": 2,
        "budget": 1,
    }

    SPEED_TIER_SCORES = {
        "very_fast": 4,
        "fast": 3,
        "moderate": 2,
        "slow": 1,
    }

    # Tier delta conversion
    TIER_DELTA_MULTIPLIER = 25  # Convert tier differences to percentage (4 tiers = 100%)


# =============================================================================
# Database & Network Configuration
# =============================================================================

class NetworkConfig:
    """Configuration réseau et timeout"""

    DB_CONNECT_TIMEOUT = 10  # Secondes - timeout pour connexion PostgreSQL
