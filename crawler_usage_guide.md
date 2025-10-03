# Website Crawler to Word Document - Usage Guide

## Overview
The `website_crawler_to_docx.py` script crawls websites and generates well-formatted Word documents with all the content from linked pages.

## Features
- **Intelligent crawling**: Follows internal links while staying within the same domain
- **Content extraction**: Extracts meaningful text content while filtering out navigation and styling elements
- **Well-formatted output**: Creates professional Word documents with:
  - Table of contents
  - Proper headings and formatting
  - Page separation
  - Metadata and timestamps

## Basic Usage

```bash
# Activate your virtual environment first
source .venv/bin/activate

# Basic usage - crawl a website
python3 website_crawler_to_docx.py https://example.com

# Specify output filename
python3 website_crawler_to_docx.py https://example.com -o my_report.docx

# Control crawling depth (default: 3)
python3 website_crawler_to_docx.py https://example.com --depth 2

# Add delay between requests (default: 1 second)
python3 website_crawler_to_docx.py https://example.com --delay 0.5
```

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `url` | Required | Starting URL to crawl |
| `-o, --output` | `website_crawl_report.docx` | Output Word document filename |
| `-d, --depth` | 3 | Maximum crawl depth |
| `--delay` | 1.0 | Delay between requests (seconds) |

## Example Results

When you ran the script on the TimeMap API website:
- **Pages crawled**: 54 pages
- **Output file**: `timemap_api_report.docx` (654 KB)
- **Content**: Complete API documentation with all endpoints and descriptions

## Dependencies

Make sure these packages are installed:
```bash
pip install requests beautifulsoup4 python-docx
```

## Tips for Best Results

1. **Respect website policies**: Always check robots.txt and terms of service
2. **Use appropriate delays**: Don't overload servers (default 1-second delay is respectful)
3. **Limit depth**: Large sites can generate huge documents - start with depth 2-3
4. **Check output**: Review the generated document to ensure quality

## Troubleshooting

- **Permission denied**: Make sure you have write permissions in the output directory
- **Large files**: Reduce crawling depth if the document becomes too large
- **Missing content**: Some dynamic content may require JavaScript - this crawler works best with static HTML
