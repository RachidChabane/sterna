"""
Core Tool Definitions

Contains all built-in tool definitions for the platform.
These are migrated from the legacy LangChain tool definitions to the new
catalog format for on-demand discovery.
"""

from .models import (
    ToolDefinition,
    ToolCategory,
    ToolProvider,
    LoadingStrategy,
    ToolInputExample,
)


# =============================================================================
# BRAVE SEARCH TOOLS
# =============================================================================

BRAVE_WEB_SEARCH = ToolDefinition(
    id="brave_web_search",
    name="Web Search",
    description="Search the web for current information, news, articles, and real-time data. Use for any query requiring up-to-date information from the internet.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["web", "search", "real-time", "news", "current-events", "internet"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=10,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-20)",
                "default": 10,
                "minimum": 1,
                "maximum": 20
            },
            "safesearch": {
                "type": "string",
                "description": "Safe search filter",
                "enum": ["off", "moderate", "strict"],
                "default": "moderate"
            },
            "freshness": {
                "type": "string",
                "description": "Result freshness: pd=past day, pw=past week, pm=past month, py=past year",
                "enum": ["", "pd", "pw", "pm", "py"],
                "default": ""
            },
            "enriched": {
                "type": "boolean",
                "description": "Return enriched results with infobox, FAQ, discussions for entities",
                "default": False
            }
        },
        "required": ["query"]
    },
    input_examples=[
        ToolInputExample(
            description="Search for recent news",
            inputs={"query": "latest AI developments 2024", "count": 10, "freshness": "pw"}
        ),
        ToolInputExample(
            description="Search for a specific entity with enriched data",
            inputs={"query": "OpenAI company", "enriched": True}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="brave_search",
    search_keywords=["search", "find", "look up", "google", "internet", "web", "query", "information"],
    search_boost=1.2,
)

BRAVE_NEWS_SEARCH = ToolDefinition(
    id="brave_news_search",
    name="News Search",
    description="Search for recent news articles and current events. Use when the user asks about headlines, breaking news, or recent developments.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["news", "articles", "current-events", "journalism", "headlines"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=11,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for news articles"
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-20)",
                "default": 10,
                "minimum": 1,
                "maximum": 20
            },
            "freshness": {
                "type": "string",
                "description": "pd=past day, pw=past week, pm=past month",
                "enum": ["", "pd", "pw", "pm"],
                "default": ""
            }
        },
        "required": ["query"]
    },
    input_examples=[
        ToolInputExample(
            description="Find recent news about a company",
            inputs={"query": "Tesla stock news", "count": 10, "freshness": "pw"}
        ),
        ToolInputExample(
            description="Get today's headlines on a topic",
            inputs={"query": "climate change", "freshness": "pd"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="brave_search",
    search_keywords=["news", "article", "headline", "current", "recent", "breaking"],
)

BRAVE_IMAGE_SEARCH = ToolDefinition(
    id="brave_image_search",
    name="Image Search",
    description="Search for images on the web. Returns image URLs, dimensions, and source information.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["images", "photos", "pictures", "visual", "media"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=12,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for images"
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-150)",
                "default": 10,
                "minimum": 1,
                "maximum": 150
            },
            "safesearch": {
                "type": "string",
                "description": "Safe search filter",
                "enum": ["off", "strict"],
                "default": "off"
            }
        },
        "required": ["query"]
    },
    input_examples=[
        ToolInputExample(
            description="Find images of a landmark",
            inputs={"query": "Eiffel Tower at night", "count": 10}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="brave_search",
    search_keywords=["image", "picture", "photo", "visual", "graphics"],
)

BRAVE_VIDEO_SEARCH = ToolDefinition(
    id="brave_video_search",
    name="Video Search",
    description="Search for videos on the web. Returns video URLs, titles, durations, and thumbnails.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["videos", "youtube", "media", "clips", "streaming"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=13,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for videos"
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-20)",
                "default": 10,
                "minimum": 1,
                "maximum": 20
            },
            "safesearch": {
                "type": "string",
                "description": "Safe search filter",
                "enum": ["off", "strict"],
                "default": "off"
            }
        },
        "required": ["query"]
    },
    input_examples=[
        ToolInputExample(
            description="Find tutorial videos",
            inputs={"query": "python machine learning tutorial", "count": 5}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="brave_search",
    search_keywords=["video", "youtube", "tutorial", "clip", "watch"],
)

FETCH_WEB_PAGE = ToolDefinition(
    id="fetch_web_page",
    name="Fetch Web Page",
    description="Fetch a web page URL and return its main content as clean markdown, stripping navigation/ads/boilerplate. Use after web search to read full articles, documentation, or any web content.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["web", "fetch", "read", "page", "url", "content", "article", "documentation"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=11,
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch (must start with http:// or https://)"
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum characters of content to return (default 5000, max 64000). Increase only if you need more detail.",
                "default": 5000,
                "minimum": 1000,
                "maximum": 64000
            },
            "extract_links": {
                "type": "boolean",
                "description": "Also return links found on the page",
                "default": False
            }
        },
        "required": ["url"]
    },
    input_examples=[
        ToolInputExample(
            description="Read a documentation page",
            inputs={"url": "https://docs.python.org/3/library/asyncio.html"}
        ),
        ToolInputExample(
            description="Read an article with links",
            inputs={"url": "https://example.com/article", "extract_links": True}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="brave_search",
    search_keywords=["fetch", "read", "page", "url", "web", "content", "article", "documentation", "open", "visit", "browse"],
    search_boost=1.2,
)

BRAVE_LOCAL_SEARCH = ToolDefinition(
    id="brave_local_search",
    name="Local Business Search",
    description="Search for local businesses and places. Returns business names, addresses, ratings, and contact info.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["local", "business", "places", "restaurants", "shops", "services"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=14,
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Business or place name to search for"
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-20)",
                "default": 5,
                "minimum": 1,
                "maximum": 20
            }
        },
        "required": ["query"]
    },
    input_examples=[
        ToolInputExample(
            description="Find restaurants nearby",
            inputs={"query": "best pizza restaurants in San Francisco", "count": 10}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="brave_search",
    search_keywords=["local", "business", "restaurant", "shop", "store", "nearby"],
)


# =============================================================================
# GOOGLE MAPS TOOLS
# =============================================================================

GEOCODE_ADDRESS = ToolDefinition(
    id="geocode_address",
    name="Geocode Address",
    description="Convert an address or place name to GPS coordinates (latitude, longitude). Use when you need to find a location on a map.",
    category=ToolCategory.LOCATION,
    provider=ToolProvider.CORE,
    tags=["maps", "location", "coordinates", "address", "geocoding", "gps"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=20,
    input_schema={
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Address or place name to convert to coordinates"
            }
        },
        "required": ["address"]
    },
    input_examples=[
        ToolInputExample(
            description="Geocode a famous landmark",
            inputs={"address": "Eiffel Tower, Paris, France"}
        ),
        ToolInputExample(
            description="Geocode a street address",
            inputs={"address": "1600 Amphitheatre Parkway, Mountain View, CA"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="google_maps",
    search_keywords=["location", "address", "coordinates", "where", "maps", "geocode", "gps"],
)

GET_DIRECTIONS = ToolDefinition(
    id="get_directions",
    name="Get Directions",
    description="Get route directions between two locations with distance, duration, and step-by-step instructions.",
    category=ToolCategory.LOCATION,
    provider=ToolProvider.CORE,
    tags=["maps", "directions", "route", "navigation", "driving", "transit"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=21,
    input_schema={
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": "Starting location (address or 'lat,lng')"
            },
            "destination": {
                "type": "string",
                "description": "Destination (address or 'lat,lng')"
            },
            "mode": {
                "type": "string",
                "description": "Travel mode",
                "enum": ["driving", "walking", "bicycling", "transit"],
                "default": "driving"
            }
        },
        "required": ["origin", "destination"]
    },
    input_examples=[
        ToolInputExample(
            description="Get driving directions between cities",
            inputs={"origin": "San Francisco, CA", "destination": "Los Angeles, CA", "mode": "driving"}
        ),
        ToolInputExample(
            description="Get walking directions",
            inputs={"origin": "Times Square, NYC", "destination": "Central Park, NYC", "mode": "walking"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="google_maps",
    search_keywords=["directions", "route", "how to get", "navigate", "travel", "distance"],
)

SEARCH_NEARBY_PLACES = ToolDefinition(
    id="search_nearby_places",
    name="Search Nearby Places",
    description="Find places of interest near a location. Returns places with ratings, addresses, and open status.",
    category=ToolCategory.LOCATION,
    provider=ToolProvider.CORE,
    tags=["maps", "places", "poi", "nearby", "restaurants", "hotels"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=22,
    input_schema={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Center point as 'latitude,longitude'"
            },
            "radius": {
                "type": "integer",
                "description": "Search radius in meters (default 1500, max 50000)",
                "default": 1500
            },
            "place_type": {
                "type": "string",
                "description": "Type of place (restaurant, cafe, museum, hotel, etc)"
            },
            "keyword": {
                "type": "string",
                "description": "Additional search keyword"
            }
        },
        "required": ["location"]
    },
    input_examples=[
        ToolInputExample(
            description="Find restaurants near coordinates",
            inputs={"location": "48.8584,2.2945", "radius": 1000, "place_type": "restaurant"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="google_maps",
    search_keywords=["nearby", "places", "find", "restaurants", "hotels", "poi", "around"],
)

GET_PLACE_DETAILS = ToolDefinition(
    id="get_place_details",
    name="Get Place Details",
    description="Get detailed information about a place including reviews, photos, opening hours, phone number, and website. Use after search_nearby_places to get full details.",
    category=ToolCategory.LOCATION,
    provider=ToolProvider.CORE,
    tags=["maps", "places", "reviews", "details", "photos", "hours"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=23,
    input_schema={
        "type": "object",
        "properties": {
            "place_id": {
                "type": "string",
                "description": "Google Place ID (from search_nearby_places results)"
            }
        },
        "required": ["place_id"]
    },
    input_examples=[
        ToolInputExample(
            description="Get details and reviews for a place",
            inputs={"place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="google_maps",
    search_keywords=["reviews", "details", "place", "rating", "hours", "photos", "phone", "website"],
)

GET_AIR_QUALITY = ToolDefinition(
    id="get_air_quality",
    name="Get Air Quality",
    description="Get current air quality index and health recommendations for a location.",
    category=ToolCategory.LOCATION,
    provider=ToolProvider.CORE,
    tags=["air", "quality", "pollution", "health", "environment", "aqi"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=24,
    input_schema={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Location as 'latitude,longitude'"
            }
        },
        "required": ["location"]
    },
    input_examples=[
        ToolInputExample(
            description="Check air quality in Paris",
            inputs={"location": "48.8566,2.3522"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="google_maps",
    search_keywords=["air", "quality", "pollution", "aqi", "health", "smog"],
)

GET_STREET_VIEW = ToolDefinition(
    id="get_street_view",
    name="Get Street View",
    description="Check if Street View is available and get an image URL for a location.",
    category=ToolCategory.LOCATION,
    provider=ToolProvider.CORE,
    tags=["street", "view", "image", "panorama", "visual"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=25,
    input_schema={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Location as 'latitude,longitude'"
            }
        },
        "required": ["location"]
    },
    input_examples=[
        ToolInputExample(
            description="Get street view of Eiffel Tower",
            inputs={"location": "48.8584,2.2945"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    feature_flag="google_maps",
    search_keywords=["street", "view", "image", "see", "visual", "panorama"],
)


# =============================================================================
# FILE SYSTEM TOOLS
# =============================================================================

EXECUTE_CODE = ToolDefinition(
    id="execute_code",
    name="Execute Code",
    description="Execute Python, JavaScript, or Bash code in a secure sandbox. Available libraries: pandas, numpy, matplotlib. For plots use plt.savefig() not plt.show().",
    category=ToolCategory.CODE_EXECUTION,
    provider=ToolProvider.CORE,
    tags=["code", "python", "javascript", "bash", "execute", "run", "script", "programming"],
    loading_strategy=LoadingStrategy.ALWAYS,  # Essential tool - always loaded
    priority=1,
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The code to execute"
            },
            "language": {
                "type": "string",
                "description": "Programming language",
                "enum": ["python", "javascript", "bash"],
                "default": "python"
            }
        },
        "required": ["code"]
    },
    input_examples=[
        ToolInputExample(
            description="Create a data visualization",
            inputs={
                "code": "import pandas as pd\nimport matplotlib.pyplot as plt\ndf = pd.read_csv('data.csv')\nplt.bar(df['x'], df['y'])\nplt.savefig('chart.png')",
                "language": "python"
            }
        ),
        ToolInputExample(
            description="List files in workspace",
            inputs={"code": "ls -la", "language": "bash"}
        ),
    ],
    is_idempotent=False,
    sandbox_isolated=True,
    feature_flag="file_tools",
    timeout_seconds=60,
    search_keywords=["code", "python", "execute", "run", "script", "program", "compute", "calculate"],
    search_boost=1.5,
    system_prompt_section="Python code execution with pandas, numpy, matplotlib available. Use plt.savefig() not plt.show().",
)

LIST_FILES = ToolDefinition(
    id="list_files",
    name="List Files",
    description="List files and directories at a path in the workspace. Use depth parameter to explore subdirectories.",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["files", "directory", "list", "browse", "explore"],
    loading_strategy=LoadingStrategy.ALWAYS,
    priority=2,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path (default: /workspace)",
                "default": "/workspace"
            },
            "depth": {
                "type": "integer",
                "description": "How deep to recurse into subdirectories (1=current dir only, 2=include immediate children, etc.). Default: 1",
                "default": 1,
                "minimum": 1,
                "maximum": 5
            }
        },
        "required": []
    },
    input_examples=[
        ToolInputExample(
            description="List root workspace",
            inputs={"path": "/workspace"}
        ),
        ToolInputExample(
            description="List with subdirectories",
            inputs={"path": "/workspace/src", "depth": 2}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["list", "files", "directory", "folder", "browse", "ls"],
)

READ_FILE = ToolDefinition(
    id="read_file",
    name="Read File",
    description="Read file contents from workspace. For LARGE files (100+ lines), use max_lines or line ranges to save tokens.",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["file", "read", "open", "content", "view", "partial"],
    loading_strategy=LoadingStrategy.ALWAYS,
    priority=3,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Full file path (e.g., '/workspace/app.py')"
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return. Use for large files to save tokens."
            },
            "from_end": {
                "type": "boolean",
                "description": "If true with max_lines, read last N lines instead of first N (like tail)"
            },
            "start_line": {
                "type": "integer",
                "description": "Start line number (1-indexed). Use with end_line for specific ranges."
            },
            "end_line": {
                "type": "integer",
                "description": "End line number (1-indexed, inclusive). Use with start_line."
            },
            "summary_only": {
                "type": "boolean",
                "description": "Return only file structure (functions, classes, imports) without code."
            }
        },
        "required": ["path"]
    },
    input_examples=[
        ToolInputExample(
            description="Read a Python file",
            inputs={"path": "/workspace/main.py"}
        ),
        ToolInputExample(
            description="Read first 50 lines of a large file",
            inputs={"path": "/workspace/large.py", "max_lines": 50}
        ),
        ToolInputExample(
            description="Read lines 100-150 of a file",
            inputs={"path": "/workspace/app.py", "start_line": 100, "end_line": 150}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["read", "file", "open", "content", "view", "cat", "head", "tail", "partial"],
)

WRITE_FILE = ToolDefinition(
    id="write_file",
    name="Write File",
    description="Create a new file with content. Use relative paths. For modifying existing files, prefer edit_file.",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["file", "write", "create", "save", "new"],
    loading_strategy=LoadingStrategy.ALWAYS,
    priority=4,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path - use relative path (e.g., 'myfile.txt')"
            },
            "content": {
                "type": "string",
                "description": "File content to write"
            }
        },
        "required": ["path", "content"]
    },
    input_examples=[
        ToolInputExample(
            description="Create a new Python file",
            inputs={"path": "hello.py", "content": "print('Hello, World!')"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=False,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["write", "file", "create", "save", "new"],
)

EDIT_FILE = ToolDefinition(
    id="edit_file",
    name="Edit File",
    description="Edit an existing file by replacing content. PREFERRED way to modify files. Workflow: 1) read_file first, 2) use edit_file to replace content.",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["file", "edit", "modify", "update", "replace"],
    loading_strategy=LoadingStrategy.ALWAYS,
    priority=5,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (e.g., '/workspace/app.py')"
            },
            "old_content": {
                "type": "string",
                "description": "Text to find (must be unique in file)"
            },
            "new_content": {
                "type": "string",
                "description": "Replacement text"
            }
        },
        "required": ["path", "old_content", "new_content"]
    },
    input_examples=[
        ToolInputExample(
            description="Fix a bug in code",
            inputs={
                "path": "/workspace/app.py",
                "old_content": "return x + y",
                "new_content": "return x * y"
            }
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=False,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["edit", "modify", "update", "change", "replace", "fix"],
    search_boost=1.3,
)

CREATE_DIRECTORY = ToolDefinition(
    id="create_directory",
    name="Create Directory",
    description="Create a directory. Parent directories are created automatically if needed.",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["directory", "folder", "create", "mkdir"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=30,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path (e.g., '/workspace/src')"
            }
        },
        "required": ["path"]
    },
    input_examples=[
        ToolInputExample(
            description="Create a source directory",
            inputs={"path": "/workspace/src/components"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["directory", "folder", "create", "mkdir"],
)

DELETE_FILE = ToolDefinition(
    id="delete_file",
    name="Delete File",
    description="Delete a file or directory. Cannot be undone!",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["file", "delete", "remove", "rm"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=31,
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to delete (e.g., '/workspace/file.txt')"
            }
        },
        "required": ["path"]
    },
    input_examples=[
        ToolInputExample(
            description="Delete a file",
            inputs={"path": "/workspace/temp.txt"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=True,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["delete", "remove", "rm", "erase"],
)

RENAME_FILE = ToolDefinition(
    id="rename_file",
    name="Rename File",
    description="Rename or move a file or directory.",
    category=ToolCategory.FILE_SYSTEM,
    provider=ToolProvider.CORE,
    tags=["file", "rename", "move", "mv"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=32,
    input_schema={
        "type": "object",
        "properties": {
            "old_path": {
                "type": "string",
                "description": "Current path (e.g., '/workspace/old.txt')"
            },
            "new_path": {
                "type": "string",
                "description": "New path (e.g., '/workspace/new.txt')"
            }
        },
        "required": ["old_path", "new_path"]
    },
    input_examples=[
        ToolInputExample(
            description="Rename a file",
            inputs={"old_path": "/workspace/draft.py", "new_path": "/workspace/main.py"}
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=False,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["rename", "move", "mv"],
)


# =============================================================================
# IMAGE GENERATION TOOLS
# =============================================================================

GENERATE_IMAGE = ToolDefinition(
    id="generate_image",
    name="Generate Image",
    description="Generate images from text descriptions using AI (Nano Banana models). Use when user asks to create, draw, generate, visualize, or make an image.",
    category=ToolCategory.MEDIA,
    provider=ToolProvider.CORE,
    tags=["image", "generation", "art", "creative", "visual", "picture", "draw", "create"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=15,
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the image to generate. Include style, composition, lighting, mood, and subjects."
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Image aspect ratio",
                "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "default": "1:1"
            },
            "resolution": {
                "type": "string",
                "description": "Output resolution: 1K (fast), 2K (balanced), 4K (highest quality, slower)",
                "enum": ["1K", "2K", "4K"],
                "default": "1K"
            }
        },
        "required": ["prompt"]
    },
    input_examples=[
        ToolInputExample(
            description="Generate a landscape photo",
            inputs={
                "prompt": "A serene mountain lake at sunset with snow-capped peaks reflecting in crystal clear water, photorealistic style",
                "aspect_ratio": "16:9",
                "resolution": "2K"
            }
        ),
        ToolInputExample(
            description="Generate a cartoon character",
            inputs={
                "prompt": "A cute cartoon cat wearing a wizard hat, sitting on a stack of books, digital art style",
                "aspect_ratio": "1:1"
            }
        ),
        ToolInputExample(
            description="Generate a high-quality logo design",
            inputs={
                "prompt": "Modern minimalist logo for a coffee shop called 'Morning Brew', clean lines, earth tones, professional",
                "aspect_ratio": "1:1",
                "resolution": "4K"
            }
        ),
    ],
    is_idempotent=False,
    is_async=True,
    timeout_seconds=120,
    feature_flag="image_generation",
    search_keywords=["image", "picture", "photo", "draw", "create", "generate", "art", "illustration", "design", "logo", "visual", "graphic"],
    search_boost=1.3,
    system_prompt_section="Image generation with Nano Banana models. Be specific about style, composition, lighting. Use aspect_ratio 16:9 for landscape, 9:16 for portrait.",
)

EDIT_IMAGE = ToolDefinition(
    id="edit_image",
    name="Edit Image",
    description="Edit or modify an existing image based on a text description. Use to add, remove, or change elements in images.",
    category=ToolCategory.MEDIA,
    provider=ToolProvider.CORE,
    tags=["image", "edit", "modify", "inpainting", "change"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=16,
    input_schema={
        "type": "object",
        "properties": {
            "image_url": {
                "type": "string",
                "description": "URL of the image to edit (can be an asset URL from previous generation)"
            },
            "prompt": {
                "type": "string",
                "description": "Description of the edit to make"
            }
        },
        "required": ["image_url", "prompt"]
    },
    input_examples=[
        ToolInputExample(
            description="Add elements to an image",
            inputs={
                "image_url": "/api/workspaces/assets/abc123/download/",
                "prompt": "Add a rainbow in the sky"
            }
        ),
        ToolInputExample(
            description="Change colors in an image",
            inputs={
                "image_url": "/api/workspaces/assets/abc123/download/",
                "prompt": "Make the car red instead of blue"
            }
        ),
    ],
    is_idempotent=False,
    is_async=True,
    timeout_seconds=120,
    feature_flag="image_generation",
    search_keywords=["edit", "modify", "change", "inpaint", "update", "alter"],
)


# =============================================================================
# VIDEO GENERATION TOOLS
# =============================================================================

GENERATE_VIDEO = ToolDefinition(
    id="generate_video",
    name="Generate Video",
    description="Generate videos from text descriptions using AI (OpenAI Sora). Use when user asks to create, generate, or make a video or animation.",
    category=ToolCategory.MEDIA,
    provider=ToolProvider.CORE,
    tags=["video", "generation", "animation", "creative", "visual", "movie", "clip", "sora"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=17,
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the video to generate. Be specific about scene, action, camera movement, lighting, and style."
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Video length in seconds (5-20)",
                "default": 5
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Video aspect ratio: '16:9' (landscape), '9:16' (portrait), '1:1' (square)",
                "enum": ["16:9", "9:16", "1:1"],
                "default": "16:9"
            }
        },
        "required": ["prompt"]
    },
    input_examples=[
        ToolInputExample(
            description="Generate a cinematic nature video",
            inputs={
                "prompt": "A majestic eagle soaring through mountain peaks at golden hour, slow motion, cinematic camera tracking shot, dramatic lighting with sun rays breaking through clouds",
                "duration_seconds": 10,
                "aspect_ratio": "16:9"
            }
        ),
        ToolInputExample(
            description="Generate a social media vertical video",
            inputs={
                "prompt": "A cup of coffee being poured in slow motion, steam rising, cozy cafe atmosphere, close-up shot, warm lighting",
                "duration_seconds": 5,
                "aspect_ratio": "9:16"
            }
        ),
    ],
    is_idempotent=False,
    is_async=True,
    timeout_seconds=300,  # Video generation can take several minutes
    feature_flag="video_generation",
    search_keywords=["video", "movie", "clip", "animation", "generate", "create", "sora", "motion", "film"],
    search_boost=1.3,
    system_prompt_section="Video generation with OpenAI Sora. Be specific about scene, action, camera movement. Generation takes 1-5 minutes.",
)


ANIMATE_IMAGE = ToolDefinition(
    id="animate_image",
    name="Animate Image",
    description="Animate a static image into a video. Bring photos to life with AI-powered motion. Use when user wants to animate a picture, add motion to an image, or create a video from a photo.",
    category=ToolCategory.MEDIA,
    provider=ToolProvider.CORE,
    tags=["video", "animation", "image", "animate", "motion", "creative", "visual"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=17,
    input_schema={
        "type": "object",
        "properties": {
            "image_url": {
                "type": "string",
                "description": "URL of the image to animate. Can be a public URL or an internal asset URL (/api/workspaces/assets/{id}/download/)."
            },
            "prompt": {
                "type": "string",
                "description": "Optional text prompt to guide the animation motion, camera movement, and effects."
            },
            "duration": {
                "type": "integer",
                "description": "Video length in seconds: 5 or 10",
                "enum": [5, 10],
                "default": 5
            }
        },
        "required": ["image_url"]
    },
    input_examples=[
        ToolInputExample(
            description="Animate a landscape photo",
            inputs={
                "image_url": "/api/workspaces/assets/abc123/download/",
                "prompt": "Gentle wind blowing through trees, clouds moving slowly across sky",
                "duration": 5
            }
        ),
    ],
    is_idempotent=False,
    is_async=True,
    timeout_seconds=300,
    feature_flag="video_generation",
    search_keywords=["animate", "image", "video", "motion", "bring to life", "photo", "picture", "movement"],
    search_boost=1.3,
    system_prompt_section="Animate static images into videos. Requires an image URL (user-uploaded or public).",
)

UPSCALE_VIDEO = ToolDefinition(
    id="upscale_video",
    name="Upscale Video",
    description="Upscale a video to 4x higher resolution using AI. Enhance low-resolution videos to high quality. Use when user wants to improve video quality, upscale, or enhance resolution.",
    category=ToolCategory.MEDIA,
    provider=ToolProvider.CORE,
    tags=["video", "upscale", "resolution", "enhance", "quality", "4k"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=17,
    input_schema={
        "type": "object",
        "properties": {
            "video_url": {
                "type": "string",
                "description": "URL of the video to upscale. Can be a public URL or an internal asset URL. Max 30 seconds."
            }
        },
        "required": ["video_url"]
    },
    input_examples=[
        ToolInputExample(
            description="Upscale a user-uploaded video",
            inputs={
                "video_url": "/api/workspaces/assets/abc123/download/"
            }
        ),
    ],
    is_idempotent=False,
    is_async=True,
    timeout_seconds=300,
    feature_flag="video_generation",
    search_keywords=["upscale", "resolution", "enhance", "quality", "4k", "video", "improve"],
    search_boost=1.2,
    system_prompt_section="Upscale videos to 4x resolution. Requires a video URL.",
)

ANIMATE_CHARACTER = ToolDefinition(
    id="animate_character",
    name="Animate Character",
    description="Animate a character using a reference performance video (Act Two). The character mimics facial expressions, lip movements, and gestures from the reference video. Use when user wants to animate a face, create a performance-driven character video, or apply expressions to a character.",
    category=ToolCategory.MEDIA,
    provider=ToolProvider.CORE,
    tags=["video", "character", "animation", "face", "performance", "act-two", "expressions", "gestures"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=17,
    input_schema={
        "type": "object",
        "properties": {
            "image_url": {
                "type": "string",
                "description": "URL of the character image or video showing a recognizable face. Can be a public URL or an internal asset URL."
            },
            "reference_video_url": {
                "type": "string",
                "description": "URL of the reference performance video (3-30 seconds). A video of a person performing (talking, expressing, gesturing). Supported: MP4, WebM, MOV."
            }
        },
        "required": ["image_url", "reference_video_url"]
    },
    input_examples=[
        ToolInputExample(
            description="Animate a character with a performance reference video",
            inputs={
                "image_url": "/api/workspaces/assets/abc123/download/",
                "reference_video_url": "/api/workspaces/assets/def456/download/"
            }
        ),
    ],
    is_idempotent=False,
    is_async=True,
    timeout_seconds=300,
    feature_flag="video_generation",
    search_keywords=["animate", "character", "performance", "face", "expressions", "gestures", "act-two", "avatar", "portrait", "motion"],
    search_boost=1.4,
    system_prompt_section="Animate characters using a reference performance video (Act Two). Requires a character image/video URL and a reference performance video URL (3-30 seconds).",
)


# =============================================================================
# REPOSITORY TOOLS
# =============================================================================

CLONE_REPO = ToolDefinition(
    id="clone_repo",
    name="Clone Repository",
    description="Clone a GitHub repository into the workspace for the coding agent to explore and modify. Use this when the user wants to work on a GitHub repository, add features, fix bugs, or create PRs.",
    category=ToolCategory.CODE_EXECUTION,
    provider=ToolProvider.CORE,
    tags=["github", "repository", "clone", "git", "code", "project"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=4,  # High priority for repo work
    input_schema={
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": "GitHub repository (owner/repo format or full URL like https://github.com/owner/repo)"
            },
            "branch": {
                "type": "string",
                "description": "Branch to clone (optional, defaults to default branch)"
            }
        },
        "required": ["repo_url"]
    },
    input_examples=[
        ToolInputExample(
            description="Clone a repository by owner/repo",
            inputs={"repo_url": "facebook/react"}
        ),
        ToolInputExample(
            description="Clone a specific branch",
            inputs={"repo_url": "vercel/next.js", "branch": "canary"}
        ),
        ToolInputExample(
            description="Clone from full URL",
            inputs={"repo_url": "https://github.com/anthropics/anthropic-sdk-python"}
        ),
    ],
    is_idempotent=False,
    timeout_seconds=300,  # 5 minutes for large repos
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["clone", "github", "repository", "repo", "git", "project", "codebase"],
    search_boost=1.4,
    system_prompt_section="Clone GitHub repositories for exploration and modification. User must have GitHub connected via MCP.",
)


# =============================================================================
# CODING AGENT TOOLS
# =============================================================================

CODING_AGENT = ToolDefinition(
    id="coding_agent",
    name="Coding Agent",
    description="Delegate complex coding tasks to the Coding Agent (an autonomous AI coding agent). Use this tool when the task requires multiple steps like exploring a codebase, writing/editing multiple files, running tests, or completing a feature. The agent can read files, write code, run bash commands, and iterate until the task is complete.",
    category=ToolCategory.CODE_EXECUTION,
    provider=ToolProvider.CORE,
    tags=["code", "agent", "autonomous", "programming", "refactor", "implement", "fix", "debug", "agentic"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=5,  # High priority for coding tasks
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The coding task to accomplish. Be specific about the desired outcome, files to modify, and any constraints or requirements."
            },
            "sub_agent": {
                "type": "string",
                "description": "Name of a specific sub-agent to run this task with (e.g. 'security-reviewer'). The task will be executed by that sub-agent instead of the default coding agent. Use list_coding_agents to see available sub-agents."
            },
            "allowed_tools": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
                },
                "description": "Tools the agent can use. Defaults to safe file operations.",
                "default": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
            },
            "max_iterations": {
                "type": "integer",
                "description": "Maximum agentic iterations before stopping (default: 20, max: 100)",
                "default": 20,
                "minimum": 1,
                "maximum": 100
            }
        },
        "required": ["task"]
    },
    input_examples=[
        ToolInputExample(
            description="Refactor a function for better performance",
            inputs={
                "task": "Refactor the calculate_total function in src/utils.py to use list comprehension instead of a for loop, and add type hints",
            }
        ),
        ToolInputExample(
            description="Implement a new feature",
            inputs={
                "task": "Add input validation to the user registration form in components/RegisterForm.tsx. Validate email format, password strength (min 8 chars, 1 number, 1 special char), and show inline error messages.",
                "max_iterations": 30
            }
        ),
        ToolInputExample(
            description="Debug and fix a failing test",
            inputs={
                "task": "The test_user_authentication test in tests/test_auth.py is failing. Investigate why and fix the underlying bug.",
                "allowed_tools": ["Read", "Edit", "Bash", "Grep"]
            }
        ),
        ToolInputExample(
            description="Run a specific sub-agent on the codebase",
            inputs={
                "task": "Review the authentication module for security vulnerabilities",
                "sub_agent": "security-reviewer"
            }
        ),
    ],
    allowed_callers=["code_execution"],
    is_idempotent=False,  # Modifies files
    is_async=True,
    estimated_latency_ms=30000,  # 30 seconds average
    timeout_seconds=600,  # 10 minutes max
    sandbox_isolated=True,
    feature_flag="coding_agent",
    search_keywords=[
        "code", "agent", "autonomous", "implement", "refactor", "fix", "debug",
        "feature", "function", "class", "module", "test", "bug", "complex",
        "multi-step", "multiple files", "codebase", "project"
    ],
    search_boost=1.4,
    system_prompt_section="Coding Agent for complex multi-step coding tasks. Delegates to an autonomous AI that can explore codebases, write/edit code, run commands, and iterate. Use for tasks requiring multiple operations across files.",
)

# All Repository tools
REPOSITORY_TOOLS = [
    CLONE_REPO,
]

# All Coding Agent tools
CODING_AGENT_TOOLS = [
    CODING_AGENT,
]


# =============================================================================
# PLANNING TOOLS
# =============================================================================

PLAN_IMPLEMENTATION = ToolDefinition(
    id="plan_implementation",
    name="Plan Implementation",
    description="Create a detailed implementation plan for a GitHub issue. Explores the codebase to understand architecture, identifies files to modify, and writes a step-by-step plan. Does NOT modify any code.",
    category=ToolCategory.CODE_EXECUTION,
    provider=ToolProvider.CORE,
    tags=["plan", "implementation", "github", "issue", "explore", "architecture"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=6,
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Description of what needs to be implemented (usually the issue title and body)"
            },
            "issue_number": {
                "type": "integer",
                "description": "GitHub issue number"
            },
            "issue_url": {
                "type": "string",
                "description": "Full URL to the GitHub issue"
            },
            "issue_title": {
                "type": "string",
                "description": "Title of the GitHub issue"
            }
        },
        "required": ["task"]
    },
    is_idempotent=False,
    is_async=True,
    timeout_seconds=600,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["plan", "implementation", "design", "architecture", "explore", "issue"],
    search_boost=1.3,
)

IMPLEMENT_PLAN = ToolDefinition(
    id="implement_plan",
    name="Implement Plan",
    description="Execute an approved implementation plan. Follows the plan steps in order, writes code, runs tests, and creates a pull request when complete. Requires a plan_id from a previously created plan.",
    category=ToolCategory.CODE_EXECUTION,
    provider=ToolProvider.CORE,
    tags=["implement", "execute", "plan", "code", "pr", "pull-request"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=7,
    input_schema={
        "type": "object",
        "properties": {
            "plan_id": {
                "type": "string",
                "description": "ID of the plan to implement (UUID)"
            }
        },
        "required": ["plan_id"]
    },
    is_idempotent=False,
    is_async=True,
    timeout_seconds=1200,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["implement", "execute", "build", "code", "pr", "pull request"],
    search_boost=1.3,
)

EDIT_PLAN = ToolDefinition(
    id="edit_plan",
    name="Edit Plan",
    description="Edit an existing implementation plan based on review instructions. Delegates to the coding agent to re-explore the codebase if needed and rewrite the plan. Use when the user wants to refine, review, or improve a plan before implementation (e.g. 'review for SOLID compliance', 'split step 3', 'add error handling').",
    category=ToolCategory.CODE_EXECUTION,
    provider=ToolProvider.CORE,
    tags=["edit", "plan", "review", "refine", "improve", "solid", "update"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=6,
    input_schema={
        "type": "object",
        "properties": {
            "plan_id": {
                "type": "string",
                "description": "ID of the plan to edit (UUID)"
            },
            "instructions": {
                "type": "string",
                "description": "What to change or review (e.g. 'review for SOLID compliance', 'add error handling steps', 'split step 3 into smaller steps')"
            }
        },
        "required": ["plan_id", "instructions"]
    },
    is_idempotent=False,
    is_async=True,
    timeout_seconds=600,
    sandbox_isolated=True,
    feature_flag="file_tools",
    search_keywords=["edit", "plan", "review", "refine", "update", "improve", "solid", "dry"],
    search_boost=1.3,
)

PLANNING_TOOLS = [
    PLAN_IMPLEMENTATION,
    IMPLEMENT_PLAN,
    EDIT_PLAN,
]


# =============================================================================
# KNOWLEDGE BASE TOOLS
# =============================================================================

QUERY_KNOWLEDGE_BASE = ToolDefinition(
    id="query_knowledge_base",
    name="Query Knowledge Base",
    description="Search the user's personal knowledge base for relevant information. The knowledge base contains documents the user has uploaded (PDFs, Word docs, text files, etc.). Use this when the user asks about information that might be in their documents, mentions 'my notes', 'my documents', or uses @kb/@knowledge.",
    category=ToolCategory.SEARCH,
    provider=ToolProvider.CORE,
    tags=["knowledge", "documents", "search", "rag", "personal", "notes", "files"],
    loading_strategy=LoadingStrategy.ON_DEMAND,
    priority=8,  # High priority for personal knowledge
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (1-10)",
                "default": 5,
                "minimum": 1,
                "maximum": 10
            }
        },
        "required": ["query"]
    },
    input_examples=[
        ToolInputExample(
            description="Search for API documentation",
            inputs={"query": "API rate limits and authentication", "max_results": 5}
        ),
        ToolInputExample(
            description="Find project notes",
            inputs={"query": "meeting notes from last week about product roadmap"}
        ),
        ToolInputExample(
            description="Search for code examples",
            inputs={"query": "Python database connection examples", "max_results": 3}
        ),
    ],
    is_idempotent=True,
    feature_flag="knowledge_base",
    search_keywords=["knowledge", "documents", "notes", "files", "personal", "my", "uploaded", "kb", "search"],
    search_boost=1.3,
    system_prompt_section="Query the user's personal knowledge base for relevant document excerpts. Cite sources when using retrieved information.",
)

# All Knowledge Base tools
KNOWLEDGE_BASE_TOOLS = [
    QUERY_KNOWLEDGE_BASE,
]


# =============================================================================
# TOOL COLLECTIONS
# =============================================================================

# All Image Generation tools
IMAGE_GENERATION_TOOLS = [
    GENERATE_IMAGE,
    EDIT_IMAGE,
]

# All Video Generation tools
VIDEO_GENERATION_TOOLS = [
    GENERATE_VIDEO,
    ANIMATE_IMAGE,
    ANIMATE_CHARACTER,
]

# All Brave Search tools (includes fetch_web_page since it shares the brave_search feature flag)
BRAVE_SEARCH_TOOLS = [
    BRAVE_WEB_SEARCH,
    BRAVE_NEWS_SEARCH,
    BRAVE_IMAGE_SEARCH,
    BRAVE_VIDEO_SEARCH,
    BRAVE_LOCAL_SEARCH,
    FETCH_WEB_PAGE,
]

# All Google Maps tools
GOOGLE_MAPS_TOOLS = [
    GEOCODE_ADDRESS,
    GET_DIRECTIONS,
    SEARCH_NEARBY_PLACES,
    GET_PLACE_DETAILS,
    GET_AIR_QUALITY,
    GET_STREET_VIEW,
]

# All File System tools
FILE_TOOLS = [
    EXECUTE_CODE,
    LIST_FILES,
    READ_FILE,
    WRITE_FILE,
    EDIT_FILE,
    CREATE_DIRECTORY,
    DELETE_FILE,
    RENAME_FILE,
]

# All core tool definitions
CORE_TOOL_DEFINITIONS = [
    *BRAVE_SEARCH_TOOLS,
    *GOOGLE_MAPS_TOOLS,
    *FILE_TOOLS,
    *REPOSITORY_TOOLS,
    *IMAGE_GENERATION_TOOLS,
    *VIDEO_GENERATION_TOOLS,
    *PLANNING_TOOLS,
    *CODING_AGENT_TOOLS,
    *KNOWLEDGE_BASE_TOOLS,
]

# IDs of tools that should ALWAYS be loaded (essential tools)
ALWAYS_LOADED_TOOL_IDS = [
    "execute_code",
    "list_files",
    "read_file",
    "write_file",
    "edit_file",
]

# Feature flag to tool category mapping
FEATURE_TO_CATEGORY = {
    "brave_search": ToolCategory.SEARCH,
    "google_maps": ToolCategory.LOCATION,
    "file_tools": [ToolCategory.FILE_SYSTEM, ToolCategory.CODE_EXECUTION],
    "image_generation": ToolCategory.MEDIA,
    "video_generation": ToolCategory.MEDIA,
    "coding_agent": ToolCategory.CODE_EXECUTION,
    "knowledge_base": ToolCategory.SEARCH,
}

# Category to feature flag mapping (reverse)
CATEGORY_TO_FEATURE = {
    ToolCategory.SEARCH: "brave_search",
    ToolCategory.LOCATION: "google_maps",
    ToolCategory.FILE_SYSTEM: "file_tools",
    ToolCategory.CODE_EXECUTION: "file_tools",
    ToolCategory.MEDIA: "image_generation",
}
