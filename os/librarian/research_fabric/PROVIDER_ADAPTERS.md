# Research Provider Adapters

Librarian OS must use whatever capabilities are actually available in its runtime.

## Web discovery adapters
Possible adapters:
- native model/web search
- Exa-like semantic/neural search
- Tavily-like search/research APIs
- Brave/Bing/Google-compatible search adapters
- custom search endpoints

## Web acquisition adapters
- direct HTTP fetch where authorized
- browser / cloud-browser tools
- Firecrawl-like crawl/extract adapters
- sitemap / RSS ingestion
- repository readers
- document/file connectors

## Scholarly adapters
- Crossref metadata
- OpenAlex
- Semantic Scholar where available
- PubMed / Europe PMC for biomedical topics
- arXiv and discipline repositories
- DOI resolution
- Retraction / correction checks where relevant

Crossref, for example, exposes public scholarly metadata and supports works, journals, funders, licences and filtering; metadata access does not imply access to the underlying full text.

## Connector adapters
- user-authorized Drive / Notion / GitHub / Gmail / CRM data
- MCP
- Composio
- local filesystem / private knowledge bases

## Capability rule
The router first discovers capabilities. It must never pretend that an adapter, API key, browser, subscription or full-text access exists.
