# core/scraper.py
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
import cloudscraper
import re
import math
import traceback
from PySide6.QtCore import QSize

# --- Helper Functions ---
def format_size(size_bytes):
    """Converts bytes to human-readable format."""
    if size_bytes is None or not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return "N/A"
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    try:
        if size_bytes < 1: # Avoid log(0) or log(<1)
            i = 0
        else:
            i = int(math.floor(math.log(size_bytes, 1024)))
            # Ensure index doesn't exceed tuple length (handles massive sizes)
            if i >= len(size_name):
                i = len(size_name) - 1
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2) if p > 0 else 0
        return f"{s} {size_name[i]}"
    except (ValueError, TypeError):
        return "N/A"

# --- Data Classes ---
@dataclass
class ScrapeResult:
    """Holds data for a single torrent entry in search results."""
    category: str
    name: str
    link: str # URL to the torrent's detail page
    magnet_link: str
    size: str # Human-readable size string from Nyaa
    date: str # Date string from Nyaa
    seeders: int
    leechers: int
    downloads: int # Completed downloads count from Nyaa
    uploader: str = "Anonymous"
    size_bytes: int = 0 # Add the size in bytes for filtering

@dataclass
class FileInfo:
    """Holds information about a single file within a torrent."""
    name: str
    size_bytes: int = 0
    size_str: str = "N/A" # Human-readable size string

@dataclass
class TorrentDetails:
    """Holds detailed information scraped from a torrent's Nyaa page."""
    title: str = "N/A"
    category: str = "N/A"
    submitter: str = "N/A"
    date_submitted: str = "N/A"
    size_str: str = "N/A"
    seeders: int | None = None
    leechers: int | None = None
    completed: int | None = None
    info_hash: str = "N/A"
    description: str = "No description available."
    file_list: list[FileInfo] = field(default_factory=list)
    information: str = "N/A" # Raw text from the 'Information' field (may overlap with others)
    magnet_link: str = ""
    image_urls: list[str] = field(default_factory=list) # List to store image URLs
    comments: list[dict] = field(default_factory=list)

# --- Scraper Class ---
class NyaaScraper:
    """Handles scraping search results and torrent details from Nyaa.si."""
    BASE_URL = "https://nyaa.si"
    # Sort options mapping UI name to URL parameter
    SORT_OPTIONS = {
        "date": "id", # Nyaa uses 'id' for date sorting internally
        "seeders": "seeders",
        "leechers": "leechers",
        "size": "size",
        "name": "name"
    }
    SORT_DEFAULT = "id"
    ORDER_DEFAULT = "desc"

    # --- Modified __init__ with Proxy Support ---
    def __init__(self, cloudflare_delay=10, proxy_config: dict = None):
        """Initializes the scraper with a cloudscraper session.

        Args:
            cloudflare_delay (int): Delay in seconds for Cloudflare challenges.
            proxy_config (dict): Dictionary with proxy details, e.g.,
                {'type': 'http', 'host': '...', 'port': '...', 'username': '...', 'password': '...'}
        """
        self.current_delay = cloudflare_delay # Store it if needed later
        self.proxy_dict = self._format_proxy(proxy_config)

        init_message = f"Initializing NyaaScraper session with delay: {cloudflare_delay}s"
        if self.proxy_dict:
            init_message += f", using proxy: {list(self.proxy_dict.values())[0].split('@')[0]}..."
        print(init_message)

        try:
            # Prepare scraper options
            scraper_options = {
                'browser': {
                    'browser': 'chrome',
                    'platform': 'windows',
                'desktop': True
                },
                'delay': self.current_delay
            }
            if self.proxy_dict:
                scraper_options['proxies'] = self.proxy_dict

            self.session = cloudscraper.create_scraper(
                **scraper_options
            )
            # Set common browser headers
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            })
            print("NyaaScraper session initialized.")
        except Exception as e:
            print(f"CRITICAL: Failed to initialize cloudscraper session: {e}")
            traceback.print_exc()
            self.session = requests.Session() # Fallback to basic requests
            print("Warning: Falling back to basic requests session. Cloudflare bypass may fail.")
            # Apply proxies to the fallback session if configured
            if self.proxy_dict:
                print("Applying proxy configuration to fallback requests session.")
                self.session.proxies.update(self.proxy_dict)

    def _format_proxy(self, config: dict) -> dict | None:
        """Formats the proxy config dict into the format requests expects."""
        if not config or config.get('type') == 'none' or not config.get('host') or not config.get('port'):
            return None

        proxy_type = config['type'].lower()
        host = config['host']
        port = config['port']
        user = config.get('username')
        password = config.get('password')

        # Basic validation
        try:
            int(port) # Check if port is a number
        except ValueError:
            print(f"ERROR: Invalid proxy port '{port}'. Proxy disabled.")
            return None

        if proxy_type not in ['http', 'socks5']:
             print(f"ERROR: Unsupported proxy type '{proxy_type}'. Proxy disabled.")
             return None

        # Build the proxy string
        proxy_url_base = f"{host}:{port}"
        if user and password:
            proxy_auth = f"{user}:{password}@"
        elif user:
            proxy_auth = f"{user}@"
        else:
            proxy_auth = ""

        if proxy_type == 'socks5':
            # Needs pysocks installed: pip install pysocks requests[socks]
            # We assume it might be installed. If not, requests will error later.
            proxy_scheme = 'socks5h' # Use socks5h for DNS resolution through proxy
        else: # http
            proxy_scheme = 'http' # Requests uses http for both http/https

        full_proxy_url = f"{proxy_scheme}://{proxy_auth}{proxy_url_base}"

        # Requests expects a dict mapping URL scheme to proxy URL
        return {
            'http': full_proxy_url,
            'https': full_proxy_url
        }

    def _parse_size_to_bytes(self, size_str: str) -> int:
        """Helper to convert size string (e.g., '1.2 GiB', '500 MiB') to bytes."""
        size_str = size_str.strip().upper()
        # Regex to capture number and unit (optional 'i' for KiB/MiB etc.)
        match = re.match(r'([\d.,]+)\s*([KMGTPEZY]?)I?B', size_str)
        if not match:
            return 0

        num_str, unit = match.groups()
        # Handle potential commas in number string
        num_str = num_str.replace(',', '')
        try:
            num = float(num_str)
        except ValueError:
            return 0 # Invalid number format

        units = {'': 0, 'K': 1, 'M': 2, 'G': 3, 'T': 4, 'P': 5, 'E': 6, 'Z': 7, 'Y': 8}
        exponent = units.get(unit, 0) # Default to 0 (Bytes) if unit is missing or unknown
        return int(num * (1024 ** exponent))

    def _parse_results(self, html_content: str) -> list[ScrapeResult]:
        """Parses the HTML of a Nyaa search results page."""
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []

        # Check for Cloudflare challenge indicators first
        if "Checking your browser" in html_content or "DDoS protection by Cloudflare" in html_content:
            print("Parser: Cloudflare challenge page detected during parsing.")
            raise ConnectionError("Cloudflare challenge detected. Scraping blocked.")

        # Find the results table
        table_body = soup.select_one('table.torrent-list > tbody')
        if not table_body:
             no_results_msg = soup.find(string=lambda text: text and "no results found" in text.lower())
             if no_results_msg:
                  print("Parser: 'No results found' message detected on page.")
                  return []
             print("Parser WARNING: Could not find results table body (tbody).")
             return []

        rows = table_body.find_all('tr', recursive=False)

        for row_index, row in enumerate(rows):
            try:
                cols = row.find_all('td', recursive=False)
                if len(cols) < 8:
                    continue

                category_tag = cols[0].find('a')
                category = category_tag['title'].strip() if category_tag and category_tag.has_attr('title') else 'N/A'

                name_col = cols[1]
                name_links = name_col.find_all('a')
                primary_link_tag = None
                for a_tag in name_links:
                    href = a_tag.get('href', '')
                    if href.startswith('/view/'):
                        primary_link_tag = a_tag
                        break

                if primary_link_tag:
                    name = primary_link_tag.get_text(strip=True)
                    link = self.BASE_URL + primary_link_tag['href']
                else:
                    name_parts = name_col.find_all(string=True, recursive=False)
                    name = ' '.join(part.strip() for part in name_parts if part.strip()) or 'N/A'
                    link = '#'

                links_col = cols[2]
                magnet_tag = links_col.find('a', href=lambda href: href and href.startswith('magnet:?'))
                magnet_link = magnet_tag['href'] if magnet_tag else ''

                size = cols[3].get_text(strip=True)
                size_bytes = self._parse_size_to_bytes(size) # Calculate bytes

                date_tag = cols[4]
                date_str = date_tag.get_text(strip=True)

                seeders = int(cols[5].get_text(strip=True))
                leechers = int(cols[6].get_text(strip=True))
                downloads = int(cols[7].get_text(strip=True))

                # New uploader logic: Search the whole row
                uploader_tag = row.find('a', class_='username-link')
                if uploader_tag:
                    uploader = uploader_tag.get_text(strip=True)
                else:
                    # If no specific username link found in the row, assume Anonymous
                    uploader = "Anonymous"

                # --- DEBUG PRINTS --- #
                if row_index < 5: # Print for the first 5 rows
                    print(f"-- DEBUG Row {row_index+1} --")
                    print(f"Name Col HTML: {name_col}") # Print the HTML of the name column
                    print(f"Uploader Found: {uploader}")
                    print(f"------------------")
                # --- END DEBUG --- #

                results.append(ScrapeResult(
                    category=category, name=name, link=link, magnet_link=magnet_link,
                    size=size, date=date_str, seeders=seeders, leechers=leechers,
                    downloads=downloads, uploader=uploader,
                    size_bytes=size_bytes
                ))
            except (AttributeError, IndexError, ValueError, TypeError) as e:
                print(f"Parser ERROR: Skipping row {row_index+1} due to error: {type(e).__name__} - {e}")
                continue

        return results

    def search(self, query, category="0_0", sort_by="date", page=1, timeout=30, trusted_only=False, uploader=""):
        """Searches Nyaa.si and returns a list of ScrapeResult objects."""
        sort_param = self.SORT_OPTIONS.get(sort_by, self.SORT_DEFAULT)
        order_param = self.ORDER_DEFAULT # Nyaa primarily uses descending

        # Construct the final query string, including uploader if specified
        final_query = query.strip()
        if uploader and isinstance(uploader, str):
            uploader_clean = uploader.strip()
            if uploader_clean:
                uploader_term = f"uploader:{uploader_clean}"
                if final_query:
                    final_query = f"{uploader_term} {final_query}"
                else:
                    final_query = uploader_term

        params = {
            'q': final_query, # Use the combined query
            'c': category,
            's': sort_param,
            'o': order_param,
            'p': page
        }

        # Add trusted filter if requested
        if trusted_only:
            params['f'] = '2' # Nyaa's filter code for Trusted Only
        else:
            params['f'] = '0' # Default filter (No filter)

        url = self.BASE_URL
        print(f"Scraping Nyaa search: {url} with params {params}")

        try:
            self.session.headers.update({'Referer': self.BASE_URL})
            print(f"Scraper: Requesting URL: {self.BASE_URL} with params: {params}, timeout={timeout}s")
            response = self.session.get(self.BASE_URL, params=params, timeout=timeout)
            print(f"Scraper: Received response status: {response.status_code}")
            response.raise_for_status()
            if "cf_clearance" in self.session.cookies:
                print("Scraper: Cloudflare clearance cookie detected in session.")
            return self._parse_results(response.text)
        except requests.exceptions.Timeout as e:
            print(f"Scraper ERROR: Request timed out: {e}")
            raise ConnectionError(f"Connection timed out while trying to reach Nyaa.si.") from e
        except requests.exceptions.HTTPError as e:
             status_code = e.response.status_code
             print(f"Scraper ERROR: HTTP Error {status_code} for URL: {e.request.url}")
             raise ConnectionError(f"Nyaa.si returned HTTP error {status_code}.") from e
        except requests.exceptions.RequestException as e:
             print(f"Scraper ERROR: Request failed: {e} - URL: {e.request.url if e.request else 'N/A'}")
             if e.response is not None and ("Checking your browser" in e.response.text or "Cloudflare" in e.response.text):
                  print("Scraper: Cloudflare challenge likely blocked the request (RequestException).")
                  raise ConnectionError(f"Cloudflare challenge likely blocked the request.") from e
             raise ConnectionError(f"Failed to connect to Nyaa.si: {e}") from e
        except ConnectionError as e:
             print(f"Scraper ERROR: ConnectionError encountered: {e}")
             raise e
        except Exception as e:
            print(f"Scraper FATAL: An unexpected error occurred during search: {type(e).__name__} - {e}")
            traceback.print_exc()
            raise RuntimeError(f"Scraping failed due to an unexpected error.") from e

    def _parse_details(self, html_content: str, url: str) -> TorrentDetails:
        """Parses the HTML of a Nyaa torrent details page with enhanced debugging."""
        print(f"\n--- Starting Detailed Parse for: {url} ---") # Debug Start
        soup = BeautifulSoup(html_content, 'html.parser')
        details = TorrentDetails() # Initialize details object

        # Check for Cloudflare challenge indicators first
        if "Checking your browser" in html_content or "DDoS protection by Cloudflare" in html_content:
            print("Parser (Details) ERROR: Cloudflare challenge page detected during parsing.")
            raise ConnectionError("Cloudflare challenge detected on details page.")

        # Find title
        title_tag = soup.select_one('.panel-heading h3.panel-title')
        details.title = title_tag.get_text(strip=True) if title_tag else url
        print(f"DEBUG (Details): Found Title: {details.title[:60]}...")

        # Find main panel body
        panel_body = soup.select_one('.panel-body')
        if not panel_body:
             deleted_msg = soup.find(string=lambda text: text and ("torrent you are looking for does not exist" in text.lower() or "torrent has been deleted" in text.lower()))
             if deleted_msg:
                 print(f"Parser (Details): Torrent at {url} does not exist or was deleted.")
                 raise FileNotFoundError(f"Torrent at {url} does not exist or was deleted.")
             print(f"Parser (Details) ERROR: Could not find panel body on page: {url}")
             raise RuntimeError(f"Could not parse expected details page structure for {url}")
        print("DEBUG (Details): Found panel body.")

        # --- Revised Logic for Extracting Info with Debugging ---
        rows = panel_body.select('div.row')
        print(f"DEBUG (Details): Found {len(rows)} div.row elements in panel body.")
        found_any_info = False # Flag to track if any known label was found

        for row_index, row in enumerate(rows):
            # Find all 'col-md-*' divs directly within this row
            cols = row.find_all('div', class_=re.compile(r'col-md-\d+'), recursive=False)

            i = 0
            while i < len(cols) - 1:
                label_tag_container = cols[i]
                value_tag_container = cols[i+1]
                i += 2 # Move index pair

                # Try finding the label text, usually within a <strong> tag
                strong_label = label_tag_container.find('strong')
                label = strong_label.get_text(strip=True).replace(':', '').lower() if strong_label else None

                if not label:
                    # Fallback: Try getting direct text if no <strong>
                    label = label_tag_container.get_text(strip=True).replace(':', '').lower()
                    if not label:
                         continue

                # Get the raw text content of the value container first
                raw_value_text = value_tag_container.get_text(strip=True)
                print(f"DEBUG (Details): Found Label='{label}', Raw Value='{raw_value_text}'") # KEY DEBUG LINE

                value_assigned = True # Assume we assigned the value unless specific logic fails
                # --- Assign to details object based on label ---
                if label == 'submitter':
                    user_link = value_tag_container.find('a', class_='username-link')
                    anon_user = value_tag_container.find('i', class_='fa-user')
                    if user_link: details.submitter = user_link.get_text(strip=True)
                    elif anon_user: details.submitter = "Anonymous"
                    else: details.submitter = raw_value_text
                elif label == 'date':
                    details.date_submitted = raw_value_text
                elif label == 'category':
                    cat_link = value_tag_container.find('a')
                    details.category = cat_link.get_text(strip=True) if cat_link else raw_value_text
                elif label == 'file size':
                    details.size_str = raw_value_text
                elif label == 'seeders':
                    span_tag = value_tag_container.find('span')
                    s_text = span_tag.get_text(strip=True) if span_tag else raw_value_text
                    try: details.seeders = int(s_text)
                    except (ValueError, TypeError): details.seeders = None
                elif label == 'leechers':
                    span_tag = value_tag_container.find('span')
                    l_text = span_tag.get_text(strip=True) if span_tag else raw_value_text
                    try: details.leechers = int(l_text)
                    except (ValueError, TypeError): details.leechers = None
                elif label == 'completed':
                    try: details.completed = int(raw_value_text)
                    except (ValueError, TypeError): details.completed = None
                elif label == 'info hash':
                    kbd_tag = value_tag_container.find('kbd')
                    details.info_hash = kbd_tag.get_text(strip=True) if kbd_tag else raw_value_text
                elif label == 'information':
                    info_link = value_tag_container.find('a')
                    details.information = info_link['href'] if info_link else raw_value_text
                else:
                    value_assigned = False # Label didn't match known fields

                if value_assigned:
                    found_any_info = True # Mark that we successfully parsed at least one known field

        if not found_any_info:
             print("Parser (Details) WARNING: Loop finished but no known info labels (category, submitter, etc.) were found and assigned. Check selectors and HTML structure.")

        # --- Find Magnet Link ---
        magnet_tag = soup.find('a', href=lambda href: href and href.startswith('magnet:?'))
        details.magnet_link = magnet_tag['href'] if magnet_tag else ""
        print(f"DEBUG (Details): Found Magnet: {'Yes' if details.magnet_link else 'No'}")

        # --- Find Description ---
        desc_tag = soup.select_one('#torrent-description')
        details.description = str(desc_tag) if desc_tag else "No description found."
        print(f"DEBUG (Details): Found Description: {'Yes' if desc_tag else 'No'}")

        # --- Extract Image URLs ---
        image_limit = 10
        found_urls = set()
        details.image_urls = [] # Ensure list is initialized here

        # 1. Find Markdown image links: ![alt text](URL)
        # Use raw description text for regex
        raw_description_text = desc_tag.get_text() if desc_tag else ""
        markdown_matches = re.findall(r'!\[.*?\]\((.*?)\)', raw_description_text)
        for md_url in markdown_matches:
            if md_url and md_url not in found_urls:
                abs_md_url = requests.compat.urljoin(url, md_url.strip())
                if abs_md_url.startswith('http'):
                    details.image_urls.append(abs_md_url)
                    found_urls.add(md_url) # Add original found URL to prevent duplicates from other methods
                    if len(details.image_urls) >= image_limit: break

        # 2. Find <img> tags (if limit not reached)
        if len(details.image_urls) < image_limit:
            desc_soup = BeautifulSoup(details.description, 'html.parser')
            for img_tag in desc_soup.find_all('img', limit=image_limit - len(details.image_urls)):
                src = img_tag.get('src')
                if src and src not in found_urls:
                    abs_src = requests.compat.urljoin(url, src)
                    if abs_src.startswith('http'):
                        details.image_urls.append(abs_src)
                        found_urls.add(src)
                        if len(details.image_urls) >= image_limit: break

        # 3. Find <a> tags linking directly to images (if limit not reached)
        if len(details.image_urls) < image_limit:
            # Re-initialize desc_soup if not already done
            if 'desc_soup' not in locals():
                desc_soup = BeautifulSoup(details.description, 'html.parser')
            for a_tag in desc_soup.find_all('a', limit=(image_limit - len(details.image_urls)) * 2):
                href = a_tag.get('href')
                if href and any(href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) and href not in found_urls:
                    abs_href = requests.compat.urljoin(url, href)
                    if abs_href.startswith('http'):
                        details.image_urls.append(abs_href)
                        found_urls.add(href)
                        if len(details.image_urls) >= image_limit: break

        print(f"DEBUG (Details): Found {len(details.image_urls)} potential image URLs.")

        # --- Find File List ---
        file_list_container = soup.select_one('div.torrent-file-list')
        print(f"DEBUG (Details): Found File List Container: {'Yes' if file_list_container else 'No'}")
        if file_list_container:
             file_items = file_list_container.select('ul > li')
             print(f"DEBUG (Details): Found {len(file_items)} file items in list.")
             for item in file_items:
                 file_name = "N/A"
                 link_tag = item.find('a')
                 if link_tag:
                     file_name = link_tag.get_text(strip=True)
                 else:
                     full_text = item.get_text(strip=True)
                     match = re.match(r'^(.*?)\s*\([\d.,]+\s*[KMGTPEZY]?I?B\)$', full_text)
                     file_name = match.group(1).strip() if match else full_text

                 size_span = item.find('span', class_='file-size')
                 size_str = "0 B"
                 if size_span: size_str = size_span.get_text(strip=True).replace('(', '').replace(')', '')
                 size_bytes = self._parse_size_to_bytes(size_str)
                 details.file_list.append(FileInfo(name=file_name, size_bytes=size_bytes, size_str=size_str))
        else: # Single file fallback
             if not details.file_list and details.size_str != "N/A":
                 print("DEBUG (Details): Applying single file fallback logic.")
                 size_bytes = self._parse_size_to_bytes(details.size_str)
                 details.file_list.append(FileInfo(name=details.title, size_bytes=size_bytes, size_str=details.size_str))

        # Final Debug Summary
        print(f"--- Finished Detailed Parse. Final Details ---")
        print(f"Category: {details.category}")
        print(f"Submitter: {details.submitter}")
        print(f"Date: {details.date_submitted}")
        print(f"Size: {details.size_str}")
        print(f"Seeders: {details.seeders}")
        print(f"Leechers: {details.leechers}")
        print(f"Completed: {details.completed}")
        print(f"Info Hash: {details.info_hash}")
        print(f"Magnet Link Present: {'Yes' if details.magnet_link else 'No'}")
        print(f"Description Present: {'Yes' if details.description != 'No description found.' else 'No'}")
        print(f"File Count: {len(details.file_list)}")
        print(f"----------------------------------------------\n")

        # --- Find Comments --- #
        comments_container = soup.select_one('#comments')
        print(f"DEBUG (Details): Found Comments Container: {'Yes' if comments_container else 'No'}")
        if comments_container:
            comment_divs = comments_container.find_all('div', class_='comment', recursive=False)
            print(f"DEBUG (Details): Found {len(comment_divs)} comment divs.")
            for comment_div in comment_divs:
                comment_data = {'author': 'N/A', 'date': 'N/A', 'content_html': ''}

                # Find Author and Date (usually in panel-heading)
                heading = comment_div.select_one('.panel-heading')
                if heading:
                    # Author might be in a link or direct text
                    author_tag = heading.find('a', href=re.compile(r'/user/'))
                    if author_tag: comment_data['author'] = author_tag.get_text(strip=True)
                    else: # Fallback if no link (e.g., deleted user?)
                        # Try getting text before the date span
                        heading_text_parts = heading.find_all(string=True, recursive=False)
                        if heading_text_parts:
                            comment_data['author'] = heading_text_parts[0].strip()

                    # Date is usually in a span with a timestamp data attribute
                    date_span = heading.find('span', attrs={'data-timestamp': True})
                    if date_span: comment_data['date'] = date_span.get_text(strip=True)

                # Find Comment Content (in panel-body)
                body = comment_div.select_one('.panel-body .comment-content')
                if body:
                    # Preserve basic HTML within the comment body
                    comment_data['content_html'] = str(body).strip()

                # Only add if we found some content
                if comment_data['content_html']:
                    details.comments.append(comment_data)

            print(f"DEBUG (Details): Parsed {len(details.comments)} comments.")

        return details

    def get_torrent_details(self, url: str, timeout=25) -> TorrentDetails:
        """Fetches and parses the details page of a specific torrent."""
        if not url or not url.startswith(self.BASE_URL + "/view/"):
            raise ValueError("Invalid Nyaa.si view URL provided.")
        try:
            self.session.headers.update({'Referer': self.BASE_URL})
            print(f"Scraper: Requesting details URL: {url}, timeout={timeout}s")
            response = self.session.get(url, timeout=timeout)
            print(f"Scraper: Received details response status: {response.status_code}")
            response.raise_for_status()
            if "cf_clearance" in self.session.cookies:
                print("Scraper: Cloudflare clearance cookie active for details request.")

            # Normal path (without saving HTML unless error)
            return self._parse_details(response.text, url)

        except requests.exceptions.Timeout as e:
            print(f"Scraper ERROR: Request timed out fetching details: {e}")
            raise ConnectionError(f"Connection timed out getting details from {url}.") from e
        except requests.exceptions.HTTPError as e:
             status_code = e.response.status_code
             print(f"Scraper ERROR: HTTP Error {status_code} fetching details from {url}")
             if status_code == 404:
                 raise FileNotFoundError(f"Torrent not found at {url} (404).")
             else:
                 raise ConnectionError(f"Nyaa.si returned HTTP error {status_code} for details page.") from e
        except requests.exceptions.RequestException as e:
            print(f"Scraper ERROR: Request failed fetching details: {e} - URL: {url}")
            if e.response is not None and ("Checking your browser" in e.response.text or "Cloudflare" in e.response.text):
                 raise ConnectionError(f"Cloudflare challenge likely blocked the details request for {url}.") from e
            raise ConnectionError(f"Failed to connect to Nyaa.si for details: {e}") from e
        except (FileNotFoundError, ConnectionError, RuntimeError) as e:
             print(f"Scraper ERROR: Failed to get details due to: {type(e).__name__} - {e}")
             raise e
        except Exception as e:
            print(f"Scraper FATAL: An unexpected error occurred getting details: {type(e).__name__} - {e}")
            traceback.print_exc()
            # Save HTML for inspection on unexpected errors during parsing
            print(f"ERROR during parsing, saving HTML to 'debug_page.html': {e}")
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(response.text if 'response' in locals() else "Response object not available.")
            raise RuntimeError(f"Parsing details failed unexpectedly for {url}") from e