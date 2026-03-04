import argparse
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class OgImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og_image = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta" or self.og_image:
            return

        attr_map = {k.lower(): v for k, v in attrs if k and v}
        if attr_map.get("property", "").lower() == "og:image":
            self.og_image = attr_map.get("content")


def normalize_username(raw_value):
    value = raw_value.strip()
    if not value:
        raise ValueError("Username cannot be empty.")

    if "pinterest.com" in value:
        parsed = urlparse(value)
        path = parsed.path.strip("/")
        if not path:
            raise ValueError("No username found in the provided Pinterest URL.")
        return path.split("/")[0]

    return value.lstrip("@")


def fetch_profile_html(username):
    url = f"https://www.pinterest.com/{username}/"
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_og_image(html_text):
    parser = OgImageParser()
    parser.feed(html_text)
    return parser.og_image


def _normalize_escaped_url(value):
    if not value:
        return ""
    try:
        import json
        # Handle cases where the value might already have double backslashes
        # or other JSON-encoded characters like \u0026.
        return json.loads(f'"{value}"').strip()
    except Exception:
        return value.replace("\\/", "/").strip()


def _looks_like_default_og_image(url):
    return "default_open_graph_1200.png" in (url or "")


def extract_profile_image_url(html_text, username):
    # First preference: structured data for the profile person object.
    script_pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    person_url_pattern = re.compile(
        r'"@type"\s*:\s*"Person".{0,4000}?"contentUrl"\s*:\s*"([^"]+)"',
        re.DOTALL,
    )

    for script_match in script_pattern.finditer(html_text):
        script_text = script_match.group(1)
        person_match = person_url_pattern.search(script_text)
        if person_match:
            candidate = _normalize_escaped_url(person_match.group(1))
            if "pinimg.com" in candidate:
                return candidate

    escaped_username = re.escape(username)

    # Next: username-scoped user payload.
    user_scoped_pattern = re.compile(
        rf'"username"\s*:\s*"{escaped_username}".{{0,3000}}?"image_xlarge_url"\s*:\s*"([^"]+)"',
        re.DOTALL,
    )
    user_scoped_match = user_scoped_pattern.search(html_text)
    if user_scoped_match:
        candidate = _normalize_escaped_url(user_scoped_match.group(1))
        if "pinimg.com" in candidate:
            return candidate

    # Fallback: first xlarge image in payload.
    xlarge_match = re.search(r'"image_xlarge_url"\s*:\s*"([^"]+)"', html_text)
    if xlarge_match:
        candidate = _normalize_escaped_url(xlarge_match.group(1))
        if "pinimg.com" in candidate:
            return candidate

    # Last resort: og:image if it is not the default Pinterest placeholder.
    og_image = extract_og_image(html_text)
    if og_image and not _looks_like_default_og_image(og_image):
        return og_image

    return None


def guess_extension(image_url):
    path = urlparse(image_url).path
    _, ext = os.path.splitext(path)
    if ext and len(ext) <= 5:
        return ext
    return ".jpg"


def download_file(url, output_path):
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=20) as response, open(output_path, "wb") as out_file:
        out_file.write(response.read())


def download_profile_picture(username, output_dir="."):
    """Finds and downloads the profile picture for the given username.
    Returns a dict with 'status' (success/error), 'url', 'path', and 'message'."""
    try:
        html_text = fetch_profile_html(username)
        image_url = extract_profile_image_url(html_text, username)

        if not image_url:
            return {"status": "error", "message": "Could not find a public profile image."}

        # Attempt high-res upgrade
        if "pinimg.com" in image_url:
            potential_hd_urls = []
            for hd_suffix in ['originals', '750x', '600x']:
                upgraded = re.sub(r'/[^/ ]+?(_RS|x[^/ ]*?)/', f'/{hd_suffix}/', image_url)
                if upgraded != image_url and upgraded not in potential_hd_urls:
                    potential_hd_urls.append(upgraded)

            for hd_url in potential_hd_urls:
                try:
                    ext = guess_extension(hd_url)
                    output_name = f"{username}_profile_hd{ext}"
                    output_path = os.path.join(output_dir, output_name)
                    download_file(hd_url, output_path)
                    return {"status": "success", "url": hd_url, "path": output_path, "resolution": "hd"}
                except Exception:
                    pass

        # Fallback to original URL
        ext = guess_extension(image_url)
        output_name = f"{username}_profile{ext}"
        output_path = os.path.join(output_dir, output_name)
        download_file(image_url, output_path)
        return {"status": "success", "url": image_url, "path": output_path, "resolution": "original"}

    except Exception as exc:
        return {"status": "error", "message": str(exc)}

def main():
    parser = argparse.ArgumentParser(
        description="Download a Pinterest profile picture from a username."
    )
    parser.add_argument(
        "username",
        nargs="?",
        help="Pinterest username (or full profile URL). If omitted, you will be prompted.",
    )
    args = parser.parse_args()

    try:
        raw_username = args.username or input("Enter Pinterest username: ")
        username = normalize_username(raw_username)

        print(f"Searching for {username}...")
        result = download_profile_picture(username)

        if result["status"] == "success":
            print(f"URL: {result['url']}")
            print(f"Downloaded profile picture to: {result['path']}")
        else:
            print(f"Error: {result['message']}", file=sys.stderr)
            sys.exit(1)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
