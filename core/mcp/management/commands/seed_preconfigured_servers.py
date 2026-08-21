"""Management command to seed preconfigured MCP servers.

These are MCP servers available to all users.
Includes both official (from service providers) and community-built servers.

Sources:
- https://github.com/sylviangth/awesome-remote-mcp-servers
- https://github.com/punkpeye/awesome-mcp-servers
- Official documentation from each provider
- NPM registry for community packages
"""

from django.core.management.base import BaseCommand
from mcp.models import MCPServer


# Preconfigured MCP servers catalog
# is_official=True: Official from service provider
# is_official=False: Community-built / third-party
PRECONFIGURED_SERVERS = [
    # ============================================================================
    # OFFICIAL SERVERS - From service providers directly
    # ============================================================================

    # ============================================================================
    # Productivity & Collaboration (Official)
    # ============================================================================
    {
        "name": "Notion",
        "description": "Access Notion pages, databases, and blocks. Search content, create pages, and manage your workspace.",
        "icon_url": "https://www.notion.so/images/favicon.ico",
        "remote_url": "https://mcp.notion.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "Asana",
        "description": "Manage Asana tasks, projects, and workspaces. Create tasks, update status, and track team progress.",
        "icon_url": "https://asana.com/favicon.ico",
        "remote_url": "https://mcp.asana.com/sse",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "monday.com",
        "description": "Manage monday.com boards, items, and workflows. Create tasks, track projects through AI.",
        "icon_url": "https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://monday.com&size=128",
        "remote_url": "https://mcp.monday.com",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "ClickUp",
        "description": "Manage ClickUp tasks, projects, and workspaces. Create and update tasks with natural language.",
        "icon_url": "https://clickup.com/favicon.ico",
        "remote_url": "https://mcp.clickup.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
        "docs_url": "https://help.clickup.com/hc/en-us/articles/33335772678423",
    },
    {
        "name": "Todoist",
        "description": "Manage Todoist tasks and projects. Create, update, and organize tasks with natural language.",
        "icon_url": "https://todoist.com/favicon.ico",
        "remote_url": "https://ai.todoist.net/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
        "docs_url": "https://developer.todoist.com/",
    },
    {
        "name": "Linear",
        "description": "Manage Linear issues, projects, and cycles. Create issues, update status, and track engineering work.",
        "icon_url": "https://linear.app/favicon.ico",
        "remote_url": "https://mcp.linear.app/sse",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "Atlassian (Jira & Confluence)",
        "description": "Access Jira issues, Confluence pages, and search across your Atlassian workspace.",
        "icon_url": "https://wac-cdn.atlassian.com/assets/img/favicons/atlassian/favicon.png",
        "remote_url": "https://mcp.atlassian.com/v1/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "Tally",
        "description": "Access and manage Tally forms, submissions, and form data. Create surveys and collect responses.",
        "icon_url": "https://tally.so/favicon.ico",
        "remote_url": "https://api.tally.so/mcp",
        "transport_type": "http",
        "auth_type": "bearer",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "Egnyte",
        "description": "Access files, folders, and content in Egnyte cloud storage. Search, read, and manage documents.",
        "icon_url": "https://cdn.simpleicons.org/egnyte",
        "remote_url": "https://mcp-server.egnyte.com/sse",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "productivity",
        "is_official": True,
    },
    {
        "name": "Figma",
        "description": "Access Figma designs. Browse files, components, and design system elements.",
        "icon_url": "https://www.figma.com/favicon.ico",
        "remote_url": "https://mcp.figma.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "design",
        "is_official": True,
    },
    {
        "name": "Webflow",
        "description": "Manage Webflow sites and CMS. Update designs, content, and site elements through AI.",
        "icon_url": "https://webflow.com/favicon.ico",
        "remote_url": "https://mcp.webflow.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "design",
        "is_official": True,
        "docs_url": "https://developers.webflow.com/data/docs/ai-tools",
    },
    {
        "name": "Dropbox",
        "description": "Access Dropbox files and Dash. Search, manage, and share files through AI.",
        "icon_url": "https://cdn.simpleicons.org/dropbox",
        "remote_url": "https://mcp.dropbox.com/dash",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
        "docs_url": "https://help.dropbox.com/integrations/set-up-MCP-server",
    },
    {
        "name": "Box",
        "description": "Access enterprise content in Box. Search, analyze files, and manage documents securely.",
        "icon_url": "https://www.box.com/favicon.ico",
        "remote_url": "https://mcp.box.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
        "docs_url": "https://developer.box.com/guides/box-mcp/remote/",
    },

    # ============================================================================
    # Automation & Integration Platforms (Official)
    # ============================================================================
    {
        "name": "Zapier",
        "description": "Connect AI to 8,000+ apps. Trigger actions, automate workflows, and integrate services instantly.",
        "icon_url": "https://cdn.simpleicons.org/zapier",
        "remote_url": "https://actions.zapier.com/mcp/",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "automation",
        "is_official": True,
        "docs_url": "https://zapier.com/mcp",
    },
    {
        "name": "Make (Integromat)",
        "description": "Run Make scenarios from AI assistants. Trigger automation workflows with natural language.",
        "icon_url": "https://cdn.simpleicons.org/make",
        "npm_package": "make-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "automation",
        "is_official": True,
        "docs_url": "https://github.com/integromat/make-mcp-server",
    },

    # ============================================================================
    # Developer Tools & Code (Official Remote)
    # ============================================================================
    {
        "name": "GitHub",
        "description": "Access repositories, issues, pull requests. Create branches, review code, and manage workflows.",
        "icon_url": "https://github.githubassets.com/favicons/favicon.svg",
        "icon_invert_in_dark_mode": True,
        "remote_url": "https://api.githubcopilot.com/mcp/",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "developer",
        "is_official": True,
    },
    # ============================================================================
    # Developer Tools (Official Local - Company-maintained npm packages)
    # ============================================================================
    {
        "name": "Brave Search",
        "description": "Official Brave Search MCP server. Privacy-focused web search with AI summarization, local business, and image search.",
        "icon_url": "https://brave.com/static-assets/images/brave-favicon.png",
        "npm_package": "@brave/brave-search-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "data",
        "is_official": True,
        "docs_url": "https://github.com/brave/brave-search-mcp-server",
    },
    {
        "name": "Playwright",
        "description": "Official Microsoft Playwright MCP server. Browser automation with screenshots, navigation, and web interactions.",
        "icon_url": "https://playwright.dev/img/playwright-logo.svg",
        "npm_package": "@playwright/mcp",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "developer",
        "is_official": True,
        "docs_url": "https://github.com/microsoft/playwright-mcp",
    },
    {
        "name": "Browserbase",
        "description": "Official Browserbase MCP server. Cloud browser automation and web scraping infrastructure.",
        "icon_url": "https://browserbase.com/favicon.ico",
        "npm_package": "@browserbasehq/mcp-server-browserbase",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "developer",
        "is_official": True,
        "docs_url": "https://github.com/browserbase/mcp-server-browserbase",
    },
    {
        "name": "Axiom",
        "description": "Official Axiom MCP server. Query and analyze logs with Axiom Processing Language (APL).",
        "icon_url": "https://axiom.co/favicon.ico",
        "remote_url": "https://mcp.axiom.co/sse",
        "transport_type": "http",
        "auth_type": "api_key",
        "category": "developer",
        "is_official": True,
        "docs_url": "https://mcp.axiom.co",
    },
    {
        "name": "Raygun",
        "description": "Official Raygun MCP server. Access error and performance monitoring data.",
        "icon_url": "https://raygun.com/favicon.ico",
        "npm_package": "@anthropics/mcp-server-raygun",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "developer",
        "is_official": True,
        "docs_url": "https://github.com/MindscapeHQ/mcp-server-raygun",
    },
    {
        "name": "MongoDB",
        "description": "Official MongoDB MCP server. Connect to MongoDB Atlas or Community databases, run queries, manage collections.",
        "icon_url": "https://www.mongodb.com/assets/images/global/favicon.ico",
        "npm_package": "mongodb-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "data",
        "is_official": True,
        "docs_url": "https://github.com/mongodb-js/mongodb-mcp-server",
    },
    {
        "name": "Twilio",
        "description": "Official Twilio MCP server. Send SMS, make voice calls, manage conversations and serverless functions.",
        "icon_url": "https://www.twilio.com/favicon.ico",
        "npm_package": "@twilio-alpha/mcp",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "communication",
        "is_official": True,
        "docs_url": "https://www.twilio.com/en-us/blog/introducing-twilio-alpha-mcp-server",
    },
    {
        "name": "Shopify Dev",
        "description": "Official Shopify developer MCP server. Search docs, explore API schemas, build Functions, access Shopify APIs.",
        "icon_url": "https://cdn.simpleicons.org/shopify",
        "npm_package": "@shopify/dev-mcp",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "developer",
        "is_official": True,
        "docs_url": "https://shopify.dev/docs/apps/build/devmcp",
    },
    {
        "name": "Stripe (Local)",
        "description": "Official Stripe MCP server. Process payments, manage customers, subscriptions, invoices, and financial operations.",
        "icon_url": "https://stripe.com/favicon.ico",
        "npm_package": "@stripe/mcp",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "finance",
        "is_official": True,
        "docs_url": "https://docs.stripe.com/mcp",
    },
    {
        "name": "Vercel",
        "description": "Manage Vercel deployments, projects, and domains. Deploy apps and monitor performance.",
        "icon_url": "https://vercel.com/favicon.ico",
        "remote_url": "https://mcp.vercel.com",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "developer",
        "is_official": True,
    },
    {
        "name": "Sentry",
        "description": "Access error tracking and performance monitoring. View issues, analyze stack traces, manage releases.",
        "icon_url": "https://cdn.simpleicons.org/sentry",
        "remote_url": "https://mcp.sentry.dev/sse",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "developer",
        "is_official": True,
    },
    {
        "name": "Datadog",
        "description": "Query Datadog metrics, logs, and traces. Monitor infrastructure and application performance.",
        "icon_url": "https://www.datadoghq.com/favicon.ico",
        "remote_url": "https://mcp.datadoghq.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "developer",
        "is_official": True,
        "docs_url": "https://docs.datadoghq.com/bits_ai/mcp_server/",
    },
    {
        "name": "Semgrep",
        "description": "Run code security scans with Semgrep. Analyze code for vulnerabilities and security issues.",
        "icon_url": "https://semgrep.dev/favicon.ico",
        "remote_url": "https://mcp.semgrep.ai/mcp",
        "transport_type": "http",
        "auth_type": "none",
        "category": "developer",
        "is_official": True,
    },
    {
        "name": "DeepWiki",
        "description": "Access documentation and wikis for any GitHub repository. Get instant knowledge about open source projects.",
        "icon_url": "https://deepwiki.com/favicon.ico",
        "remote_url": "https://mcp.deepwiki.com/mcp",
        "transport_type": "http",
        "auth_type": "none",
        "category": "developer",
        "is_official": True,
    },
    {
        "name": "Apify",
        "description": "Run web scrapers, crawlers, and automation actors. Access Apify's cloud platform for data extraction.",
        "icon_url": "https://apify.com/favicon.ico",
        "remote_url": "https://mcp.apify.com/sse",
        "transport_type": "http",
        "auth_type": "bearer",
        "category": "data",
        "is_official": True,
    },
    {
        "name": "Firecrawl",
        "description": "Crawl and scrape websites. Convert any website to clean markdown or structured data.",
        "icon_url": "https://firecrawl.dev/favicon.ico",
        "remote_url": "https://mcp.firecrawl.dev/sse",
        "transport_type": "http",
        "auth_type": "api_key",
        "category": "data",
        "is_official": True,
    },

    # ============================================================================
    # Cloud & Infrastructure (Official)
    # ============================================================================
    {
        "name": "Supabase",
        "description": "Manage Supabase projects. Access databases, authentication, storage, and edge functions.",
        "icon_url": "https://cdn.simpleicons.org/supabase",
        "remote_url": "https://mcp.supabase.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Neon",
        "description": "Manage Neon serverless Postgres databases. Create branches, run queries, manage schemas.",
        "icon_url": "https://neon.tech/favicon.ico",
        "remote_url": "https://mcp.neon.tech/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Firebase",
        "description": "Manage Firebase projects. Access Firestore, Auth, Storage, and deploy Cloud Functions.",
        "icon_url": "https://firebase.google.com/favicon.ico",
        "npm_package": "firebase-tools",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "cloud",
        "is_official": True,
        "docs_url": "https://firebase.google.com/docs/cli/mcp-server",
    },

    # ============================================================================
    # CRM & Sales (Official)
    # ============================================================================
    {
        "name": "HubSpot",
        "description": "Access HubSpot CRM. View contacts, deals, companies, and marketing data (read-only beta).",
        "icon_url": "https://www.hubspot.com/favicon.ico",
        "remote_url": "https://mcp.hubspot.com",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "crm",
        "is_official": True,
    },
    {
        "name": "Intercom",
        "description": "Access Intercom conversations, contacts, and help center. Search and manage customer support.",
        "icon_url": "https://cdn.simpleicons.org/intercom",
        "remote_url": "https://mcp.intercom.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "crm",
        "is_official": True,
    },

    # ============================================================================
    # Finance & Payments (Official)
    # ============================================================================
    {
        "name": "Stripe",
        "description": "Access Stripe payment data. View customers, subscriptions, invoices, and payment history.",
        "icon_url": "https://stripe.com/favicon.ico",
        "remote_url": "https://mcp.stripe.com/",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "finance",
        "is_official": True,
    },
    {
        "name": "Xero",
        "description": "Access Xero accounting data. Manage invoices, contacts, and financial reports.",
        "icon_url": "https://www.xero.com/favicon.ico",
        "npm_package": "@xeroapi/xero-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "finance",
        "is_official": True,
        "docs_url": "https://github.com/XeroAPI/xero-mcp-server",
    },
    {
        "name": "QuickBooks",
        "description": "Access QuickBooks accounting data. Manage customers, invoices, and financial operations.",
        "icon_url": "https://cdn.simpleicons.org/quickbooks",
        "npm_package": "quickbooks-online-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "finance",
        "is_official": True,
        "docs_url": "https://github.com/intuit/quickbooks-online-mcp-server",
    },
    {
        "name": "Plaid",
        "description": "Access Plaid developer dashboard. Monitor integration health, API usage, and Link analytics.",
        "icon_url": "https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://plaid.com&size=128",
        "remote_url": "https://mcp.plaid.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "finance",
        "is_official": True,
        "docs_url": "https://plaid.com/docs/",
    },

    # ============================================================================
    # E-commerce (Official)
    # ============================================================================
    {
        "name": "Shopify Storefront",
        "description": "Access Shopify stores. Browse products, manage carts, and handle customer shopping.",
        "icon_url": "https://cdn.simpleicons.org/shopify",
        "remote_url": "https://shopify.dev/mcp/storefront",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "ecommerce",
        "is_official": True,
        "docs_url": "https://shopify.dev/docs/apps/build/storefront-mcp",
    },

    # ============================================================================
    # AI & Knowledge (Official)
    # ============================================================================
    {
        "name": "Supermemory",
        "description": "Store and recall information across conversations. Build a persistent memory for AI assistants.",
        "icon_url": "https://supermemory.ai/favicon.ico",
        "remote_url": "https://mcp.supermemory.ai/",
        "transport_type": "http",
        "auth_type": "bearer",
        "category": "ai",
        "is_official": True,
    },
    {
        "name": "Perplexity",
        "description": "AI-powered web search with real-time results. Deep research and conversational search.",
        "icon_url": "https://www.perplexity.ai/favicon.ico",
        "npm_package": "@perplexity-ai/mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "ai",
        "is_official": True,
        "docs_url": "https://docs.perplexity.ai/guides/mcp-server",
    },
    {
        "name": "Exa",
        "description": "Neural AI search engine. Semantic web search, code search, and content extraction.",
        "icon_url": "https://exa.ai/favicon.ico",
        "npm_package": "exa-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "ai",
        "is_official": True,
        "docs_url": "https://docs.exa.ai/reference/exa-mcp",
    },

    # ============================================================================
    # Cloudflare Services (Official - verified OAuth endpoints)
    # ============================================================================
    {
        "name": "Cloudflare Docs",
        "description": "Search and query Cloudflare documentation. Get information about Cloudflare products and features.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://docs.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare Workers",
        "description": "Manage Cloudflare Workers. Deploy, update, and monitor serverless functions at the edge.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://workers.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare R2",
        "description": "Manage Cloudflare R2 storage. Upload, download, and organize objects in R2 buckets.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://r2.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare KV",
        "description": "Manage Cloudflare Workers KV. Read and write key-value data at the edge.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://kv.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare D1",
        "description": "Manage Cloudflare D1 databases. Query and manage serverless SQLite databases.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://d1.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare Browser",
        "description": "Control a remote browser via Cloudflare. Automate web interactions and scraping.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://browser.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "developer",
        "is_official": True,
    },
    {
        "name": "Cloudflare Radar",
        "description": "Access Cloudflare Radar data. Get internet traffic insights and security trends.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://radar.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "data",
        "is_official": True,
    },
    {
        "name": "Cloudflare Observability",
        "description": "Access Cloudflare observability data. View logs, analytics, and performance metrics.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://observability.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "developer",
        "is_official": True,
    },
    {
        "name": "Cloudflare AI Gateway",
        "description": "Manage Cloudflare AI Gateway. Monitor and control AI API calls with caching and rate limiting.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://ai-gateway.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "ai",
        "is_official": True,
    },
    {
        "name": "Cloudflare Vectorize",
        "description": "Manage Cloudflare Vectorize. Store and query vector embeddings for AI applications.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://vectorize.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "ai",
        "is_official": True,
    },
    {
        "name": "Cloudflare Queues",
        "description": "Manage Cloudflare Queues. Send and receive messages for async processing.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://queues.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare Durable Objects",
        "description": "Manage Cloudflare Durable Objects. Create stateful serverless applications.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://durable-objects.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare Containers",
        "description": "Manage Cloudflare Containers. Deploy and run container workloads at the edge.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://containers.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },
    {
        "name": "Cloudflare AutoRAG",
        "description": "Access Cloudflare AutoRAG. Build and query retrieval-augmented generation pipelines.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://autorag.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "ai",
        "is_official": True,
    },
    {
        "name": "Cloudflare Bindings",
        "description": "Manage Cloudflare resource bindings. Configure connections between Workers and other services.",
        "icon_url": "https://www.cloudflare.com/favicon.ico",
        "remote_url": "https://bindings.mcp.cloudflare.com/mcp",
        "transport_type": "http",
        "auth_type": "oauth",
        "category": "cloud",
        "is_official": True,
    },

    # ============================================================================
    # COMMUNITY SERVERS - Third-party / Community-built
    # ============================================================================

    # ============================================================================
    # Google Workspace (Community NPM packages)
    # ============================================================================
    {
        "name": "Google Drive",
        "description": "Access and manage Google Drive files and folders. Search, read, upload, and organize documents.",
        "icon_url": "https://ssl.gstatic.com/docs/doclist/images/drive_2022q3_32dp.png",
        "npm_package": "@modelcontextprotocol/server-gdrive",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "productivity",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/gdrive",
    },
    {
        "name": "Google Maps",
        "description": "Access Google Maps services. Search places, get directions, geocoding, and location data.",
        "icon_url": "https://maps.google.com/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-google-maps",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "utilities",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/google-maps",
    },

    # ============================================================================
    # Developer Tools (Community)
    # ============================================================================
    {
        "name": "GitLab",
        "description": "Access GitLab repositories, issues, merge requests, and CI/CD pipelines. Manage projects and code.",
        "icon_url": "https://gitlab.com/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-gitlab",
        "transport_type": "sandboxed",
        "auth_type": "bearer",
        "category": "developer",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/gitlab",
    },
    {
        "name": "Git",
        "description": "Read, search, and manipulate Git repositories. Access commit history, branches, and file contents.",
        "icon_url": "https://git-scm.com/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-git",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "developer",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/git",
    },
    {
        "name": "GitHub (Community)",
        "description": "Access GitHub repositories via personal access token. Browse repos, issues, PRs, and code.",
        "icon_url": "https://github.githubassets.com/favicons/favicon.svg",
        "icon_invert_in_dark_mode": True,
        "npm_package": "@modelcontextprotocol/server-github",
        "transport_type": "sandboxed",
        "auth_type": "bearer",
        "category": "developer",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/github",
    },
    {
        "name": "Puppeteer",
        "description": "Browser automation with Puppeteer. Navigate pages, take screenshots, interact with elements.",
        "icon_url": "https://pptr.dev/img/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-puppeteer",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "developer",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer",
    },
    {
        "name": "Fetch",
        "description": "Fetch and convert web content to markdown. Retrieve web pages in a clean, readable format.",
        "icon_url": "https://www.google.com/s2/favicons?domain=fetch.com&sz=64",
        "npm_package": "@modelcontextprotocol/server-fetch",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "data",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    },
    {
        "name": "Filesystem",
        "description": "Secure file operations with configurable access controls. Read, write, and manage files.",
        "icon_url": "https://www.google.com/s2/favicons?domain=nodejs.org&sz=64",
        "npm_package": "@modelcontextprotocol/server-filesystem",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "developer",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
    },
    {
        "name": "Memory",
        "description": "Knowledge graph-based persistent memory. Store and retrieve information across sessions.",
        "icon_url": "https://www.google.com/s2/favicons?domain=memory.ai&sz=64",
        "npm_package": "@modelcontextprotocol/server-memory",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "ai",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
    },
    {
        "name": "Everart",
        "description": "AI image generation using Everart platform. Create images from text descriptions.",
        "icon_url": "https://everart.ai/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-everart",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "ai",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/everart",
    },
    {
        "name": "Sequential Thinking",
        "description": "Dynamic problem-solving through thought sequences. Break down complex problems step by step.",
        "icon_url": "https://www.google.com/s2/favicons?domain=thinking.ai&sz=64",
        "npm_package": "@modelcontextprotocol/server-sequential-thinking",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "ai",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
    },

    # ============================================================================
    # Communication (Community)
    # ============================================================================
    {
        "name": "Slack",
        "description": "Access Slack workspaces. Send messages, read channels, search conversations, and manage users.",
        "icon_url": "https://a.slack-edge.com/80588/marketing/img/meta/favicon-32.png",
        "npm_package": "@modelcontextprotocol/server-slack",
        "transport_type": "sandboxed",
        "auth_type": "bearer",
        "category": "communication",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/slack",
    },

    # ============================================================================
    # Database & Data (Community)
    # ============================================================================
    {
        "name": "PostgreSQL",
        "description": "Connect to PostgreSQL databases. Run queries, explore schemas, and manage data.",
        "icon_url": "https://www.postgresql.org/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-postgres",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "data",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
    },
    {
        "name": "SQLite",
        "description": "Work with SQLite databases. Run queries, manage tables, and explore local database files.",
        "icon_url": "https://www.sqlite.org/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-sqlite",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "data",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite",
    },

    # ============================================================================
    # Cloud Storage (Community)
    # ============================================================================
    {
        "name": "AWS KB Retrieval",
        "description": "Retrieve information from AWS Knowledge Bases using Bedrock Agent Runtime.",
        "icon_url": "https://a0.awsstatic.com/libra-css/images/site/fav/favicon.ico",
        "npm_package": "@modelcontextprotocol/server-aws-kb-retrieval",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "cloud",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/aws-kb-retrieval",
    },

    # ============================================================================
    # Utilities & Tools (Community)
    # ============================================================================
    {
        "name": "Time",
        "description": "Get current time and timezone conversions. Access time-related utilities.",
        "icon_url": "https://www.google.com/s2/favicons?domain=time.is&sz=64",
        "npm_package": "@modelcontextprotocol/server-time",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "utilities",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/time",
    },
    {
        "name": "Sentry (Community)",
        "description": "Access Sentry error tracking via API token. View issues, stack traces, and releases.",
        "icon_url": "https://cdn.simpleicons.org/sentry",
        "npm_package": "@modelcontextprotocol/server-sentry",
        "transport_type": "sandboxed",
        "auth_type": "bearer",
        "category": "developer",
        "is_official": False,
        "docs_url": "https://github.com/modelcontextprotocol/servers/tree/main/src/sentry",
    },

    # ============================================================================
    # Communication & Messaging (Community)
    # ============================================================================
    {
        "name": "Discord",
        "description": "Send messages, read channels, and manage Discord servers through AI.",
        "icon_url": "https://cdn.simpleicons.org/discord",
        "npm_package": "@hanweg/mcp-discord",
        "transport_type": "sandboxed",
        "auth_type": "bearer",
        "category": "communication",
        "is_official": False,
        "docs_url": "https://github.com/hanweg/mcp-discord",
    },

    # ============================================================================
    # Productivity & Scheduling (Community)
    # ============================================================================
    {
        "name": "Google Calendar",
        "description": "Manage Google Calendar events. Create, update, and query calendar entries.",
        "icon_url": "https://calendar.google.com/googlecalendar/images/favicon_v2018_256.png",
        "npm_package": "@nspady/google-calendar-mcp",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "utilities",
        "is_official": False,
        "docs_url": "https://github.com/nspady/google-calendar-mcp",
    },
    {
        "name": "Airtable",
        "description": "Access Airtable bases. Query records, update data, and manage database structures.",
        "icon_url": "https://airtable.com/favicon.ico",
        "npm_package": "airtable-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "data",
        "is_official": False,
        "docs_url": "https://github.com/domdomegg/airtable-mcp-server",
    },
    {
        "name": "Calendly",
        "description": "Manage Calendly events and scheduling. View appointments and create booking links.",
        "icon_url": "https://calendly.com/favicon.ico",
        "npm_package": "@meamitpatil/calendly-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "utilities",
        "is_official": False,
        "docs_url": "https://github.com/meamitpatil/calendly-mcp-server",
    },

    # ============================================================================
    # Customer Support (Community)
    # ============================================================================
    {
        "name": "Zendesk",
        "description": "Manage Zendesk tickets. Search, create, update support tickets through AI.",
        "icon_url": "https://www.zendesk.com/favicon.ico",
        "npm_package": "@reminia/zendesk-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "crm",
        "is_official": False,
        "docs_url": "https://github.com/reminia/zendesk-mcp-server",
    },

    # ============================================================================
    # Email Marketing (Community)
    # ============================================================================
    {
        "name": "SendGrid",
        "description": "Send emails, manage contacts, and handle email marketing campaigns.",
        "icon_url": "https://sendgrid.com/favicon.ico",
        "npm_package": "@garoth/sendgrid-mcp",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "communication",
        "is_official": False,
        "docs_url": "https://github.com/Garoth/sendgrid-mcp",
    },
    {
        "name": "Mailchimp",
        "description": "Manage Mailchimp campaigns, contacts, and email marketing operations.",
        "icon_url": "https://mailchimp.com/favicon.ico",
        "npm_package": "mailchimp-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "communication",
        "is_official": False,
        "docs_url": "https://github.com/AgentX-ai/mailchimp-mcp",
    },

    # ============================================================================
    # Developer Tools (Community)
    # ============================================================================
    {
        "name": "n8n",
        "description": "Access n8n node documentation and operations. Build workflows with AI assistance.",
        "icon_url": "https://n8n.io/favicon.ico",
        "npm_package": "@czlonkowski/n8n-mcp",
        "transport_type": "sandboxed",
        "auth_type": "none",
        "category": "automation",
        "is_official": False,
        "docs_url": "https://github.com/czlonkowski/n8n-mcp",
    },
    {
        "name": "Atlassian (Community)",
        "description": "Access Jira and Confluence via personal tokens. For Cloud and Server/Data Center.",
        "icon_url": "https://wac-cdn.atlassian.com/assets/img/favicons/atlassian/favicon.png",
        "npm_package": "mcp-atlassian",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "productivity",
        "is_official": False,
        "docs_url": "https://github.com/sooperset/mcp-atlassian",
    },

    # ============================================================================
    # Cloud Storage (Community)
    # ============================================================================
    {
        "name": "AWS S3",
        "description": "Manage AWS S3 buckets and objects. Upload, download, and organize cloud storage.",
        "icon_url": "https://a0.awsstatic.com/libra-css/images/site/fav/favicon.ico",
        "npm_package": "@awslabs/s3-mcp-server",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "cloud",
        "is_official": False,
        "docs_url": "https://awslabs.github.io/mcp/servers/s3-tables-mcp-server",
    },

    # ============================================================================
    # CRM (Community)
    # ============================================================================
    {
        "name": "Salesforce",
        "description": "Access Salesforce CRM data. Query objects, run SOQL, and manage records.",
        "icon_url": "https://www.salesforce.com/favicon.ico",
        "npm_package": "mcp-server-salesforce",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "crm",
        "is_official": False,
        "docs_url": "https://github.com/salesforcecli/mcp",
    },
    {
        "name": "HubSpot (Community)",
        "description": "Access HubSpot CRM with caching. Manage contacts, deals, and companies.",
        "icon_url": "https://www.hubspot.com/favicon.ico",
        "npm_package": "@peakmojo/mcp-hubspot",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "crm",
        "is_official": False,
        "docs_url": "https://github.com/peakmojo/mcp-hubspot",
    },

    # ============================================================================
    # Database (Community)
    # ============================================================================
    {
        "name": "Supabase (Community)",
        "description": "Connect to Supabase via PostgREST. Query and manage PostgreSQL data.",
        "icon_url": "https://cdn.simpleicons.org/supabase",
        "npm_package": "@supabase-community/supabase-mcp",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "data",
        "is_official": False,
        "docs_url": "https://github.com/supabase-community/supabase-mcp",
    },

    # ============================================================================
    # Finance (Community)
    # ============================================================================
    {
        "name": "Plaid Banking",
        "description": "Access Plaid financial data. View bank accounts, transactions, and balances.",
        "icon_url": "https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://plaid.com&size=128",
        "npm_package": "@arjabbar/plaidmcp",
        "transport_type": "sandboxed",
        "auth_type": "api_key",
        "category": "finance",
        "is_official": False,
        "docs_url": "https://github.com/arjabbar/plaidmcp",
    },

    # ============================================================================
    # Social Media & Content Publishing (Sterna MCP Servers)
    # Our own MCP servers for video publishing (packages not yet published).
    # TODO: Update npm_package values once packages are published:
    #   - @sterna/mcp-server-youtube (or chosen npm scope)
    #   - @sterna/mcp-server-tiktok (or chosen npm scope)
    # TODO: Update docs_url to actual GitHub repo URL
    # ============================================================================
    {
        "name": "YouTube",
        "description": "Upload videos to YouTube, manage playlists, and fetch channel info. One-click publishing for AI-generated videos.",
        "icon_url": "https://www.youtube.com/favicon.ico",
        "npm_package": "@sterna/mcp-server-youtube",  # TODO: Confirm npm scope
        "transport_type": "sandboxed",
        "auth_type": "oauth",
        "category": "communication",
        "is_official": False,
        "docs_url": "https://github.com/sterna/mcp-servers",  # TODO: Update to actual repo
        "allowed_domains": ["youtube.com", "www.youtube.com", "googleapis.com", "accounts.google.com", "oauth2.googleapis.com"],
    },
    {
        "name": "TikTok",
        "description": "Upload and publish videos to TikTok. Quick social media publishing for AI-generated content.",
        "icon_url": "https://www.tiktok.com/favicon.ico",
        "npm_package": "@sterna/mcp-server-tiktok",  # TODO: Confirm npm scope
        "transport_type": "sandboxed",
        "auth_type": "oauth",
        "category": "communication",
        "is_official": False,
        "docs_url": "https://github.com/sterna/mcp-servers",  # TODO: Update to actual repo
        "allowed_domains": ["tiktok.com", "www.tiktok.com", "api.tiktok.com", "open-api.tiktok.com", "open.tiktokapis.com"],
    },
]


class Command(BaseCommand):
    """Seed the database with preconfigured remote MCP servers."""

    help = "Seed preconfigured remote MCP servers available to all users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear all existing preconfigured servers before seeding",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating",
        )
        parser.add_argument(
            "--discover-tools",
            action="store_true",
            help="Discover and store tools for NPM-based servers (requires orchestrator)",
        )
        parser.add_argument(
            "--server-name",
            type=str,
            help="Only process server with this name (useful with --discover-tools)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clear = options["clear"]
        discover_tools = options["discover_tools"]
        server_name_filter = options.get("server_name")

        if clear and not dry_run:
            count = MCPServer.objects.filter(is_preconfigured=True).delete()[0]
            self.stdout.write(
                self.style.WARNING(f"Deleted {count} existing preconfigured servers")
            )

        created_count = 0
        updated_count = 0
        servers_to_process = PRECONFIGURED_SERVERS

        # Filter if specific server requested
        if server_name_filter:
            servers_to_process = [
                s for s in PRECONFIGURED_SERVERS
                if s["name"].lower() == server_name_filter.lower()
            ]
            if not servers_to_process:
                self.stdout.write(
                    self.style.ERROR(f"Server '{server_name_filter}' not found in catalog")
                )
                return

        for server_data in servers_to_process:
            name = server_data["name"]

            # Check if server already exists
            existing = MCPServer.objects.filter(
                name=name,
                is_preconfigured=True,
            ).first()

            if existing:
                if dry_run:
                    self.stdout.write(f"  Would update: {name}")
                else:
                    # Update existing server
                    for key, value in server_data.items():
                        setattr(existing, key, value)
                    existing.is_preconfigured = True
                    existing.is_active = True
                    existing.user = None
                    existing.save()
                    self.stdout.write(f"  Updated: {name}")
                updated_count += 1
                server = existing
            else:
                if dry_run:
                    self.stdout.write(f"  Would create: {name}")
                    server = None
                else:
                    # Create new preconfigured server
                    server = MCPServer.objects.create(
                        **server_data,
                        is_preconfigured=True,
                        is_active=True,
                        user=None,
                    )
                    self.stdout.write(self.style.SUCCESS(f"  Created: {name}"))
                created_count += 1

            # Discover tools if requested
            if discover_tools and server and not dry_run:
                self._discover_tools_for_server(server)

        # Summary
        total = len(servers_to_process)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry run complete. Would create {created_count}, "
                    f"update {updated_count} of {total} servers."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSeeding complete! Created {created_count}, "
                    f"updated {updated_count} of {total} remote MCP servers."
                )

            )
    def _discover_tools_for_server(self, server: MCPServer):
        """Discover and store tools for a preconfigured server.

        For NPM-based servers: Uses orchestrator to start server and discover tools.
        For remote HTTP servers: Skipped (requires user auth).
        """
        from mcp.models import MCPTool

        if not server.npm_package:
            self.stdout.write(
                f"    Skipping tool discovery for {server.name} (remote server, requires auth)"
            )
            return

        self.stdout.write(f"    Discovering tools for {server.name}...")

        try:
            import httpx
            from django.conf import settings

            orchestrator_url = getattr(
                settings, 'ORCHESTRATOR_URL', 'http://sterna-orchestrator:8003'
            )

            # Use a special "system" server ID for preconfigured servers
            server_id = f"preconfigured-{server.id}"

            # Start server in sandbox (without env vars - just for tool discovery)
            start_response = httpx.post(
                f"{orchestrator_url}/mcp/servers",
                json={
                    "server_id": server_id,
                    "npm_package": server.npm_package,
                    "env_vars": {},  # No credentials for discovery
                    "allowed_domains": server.allowed_domains or [],
                },
                timeout=60.0,
            )

            if start_response.status_code != 200:
                self.stdout.write(
                    self.style.WARNING(
                        f"    Failed to start {server.name}: {start_response.text[:100]}"
                    )
                )
                return

            # Discover tools
            tools_response = httpx.get(
                f"{orchestrator_url}/mcp/servers/{server_id}/tools",
                timeout=60.0,
            )

            if tools_response.status_code != 200:
                self.stdout.write(
                    self.style.WARNING(
                        f"    Failed to discover tools for {server.name}: {tools_response.text[:100]}"
                    )
                )
                return

            discovered_tools = tools_response.json()

            # Delete existing tools for this server (refresh)
            server.tools.all().delete()

            # Save discovered tools
            for tool_data in discovered_tools:
                MCPTool.objects.create(
                    server=server,
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    metadata={},
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"    Discovered {len(discovered_tools)} tools for {server.name}"
                )
            )

            # Stop the server
            httpx.post(
                f"{orchestrator_url}/mcp/servers/{server_id}/stop",
                timeout=30.0,
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"    Error discovering tools for {server.name}: {e}")
            )
