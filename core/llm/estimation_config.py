"""
Centralized constants for token and cost estimation.
Avoid magic numbers by defining shared defaults here.
"""

# Heuristic: approximate characters per token when no tokenizer available
CHARS_PER_TOKEN = 4

# Safety reserve tokens to keep headroom for stop sequences/formatting
SAFETY_COMPLETION_RESERVE = 32

# Weights for completion estimate based on input origin
TYPED_WEIGHT = 1.3
FILES_WEIGHT = 0.25

# Minimum completion floors depending on typed-text presence
MIN_COMPLETION_IF_TYPED_SMALL = 50       # when typed tokens are small (<20)
MIN_COMPLETION_IF_TYPED_PRESENT = 100    # when typed tokens are reasonable
MIN_COMPLETION_IF_NO_TYPED = 32          # when only files contribute text

# Fallbacks
DEFAULT_COMPLETION_GUESS = 500           # used when no breakdown is provided
DEFAULT_MAX_TOKENS_FALLBACK = 8192       # conservative default if model missing

# Fallback pricing per 1K tokens if catalog lacks pricing
FALLBACK_PROMPT_PRICE_PER_1K = 0.01
FALLBACK_COMPLETION_PRICE_PER_1K = 0.02

# Default alpha and beta coefficients for completion estimate when not provided
ALPHA_T_DEFAULT = 100.0
BETA_T_DEFAULT = 0.30

# Absolute cap to avoid unrealistic completions
ABS_COMPLETION_CAP = 2048

# Cap the linear term input P in alpha + beta*P to avoid runaway estimates for very large prompts
LINEAR_P_CAP = 4000  # tokens

# Summarization-specific boosts (centralized to avoid magic numbers)
SUMMARIZATION_FILE_BOOST_PER_FILE = 192          # tokens added per attached file
SUMMARIZATION_FILE_BOOST_MAX_FILES = 10          # cap number of files counted for boost
SUMMARIZATION_PROMPT_PERCENT_BOOST = 0.12        # additional percentage of P_eff added

# Keyword scaling for alpha/beta when primary-task keywords are present in typed text
KEYWORD_SCALE_PER_HIT = 0.1                      # +10% per keyword hit for primary task
KEYWORD_SCALE_MAX = 2.0                          # cap total scaling to 2x

# Image prompt token estimation (heuristics)
IMAGE_PROMPT_BASE_TOKENS = 256                   # base token cost per image
IMAGE_PROMPT_TOKENS_PER_MB = 700                 # tokens per megabyte when dimensions unknown
IMAGE_PROMPT_TOKENS_PER_MP = 350                 # tokens per megapixel when width/height known
IMAGE_PROMPT_TOKENS_CAP_PER_IMAGE = 2048         # cap token contribution per image
IMAGE_MAX_COUNT = 16                             # cap number of images counted
IMAGE_LINEAR_WEIGHT = 0.25                       # weight of image tokens in linear completion term
