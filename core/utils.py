from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def file_url_to_path(file_url: str) -> Path:
    """Convert a file:// URI (e.g. an MCP root URI) to a local Path.

    Handles Windows drive letters (file:///C:/videos) and percent-encoded
    characters (file:///C:/my%20videos).
    """
    parsed = urlparse(str(file_url))
    if parsed.scheme != "file":
        raise ValueError(f"Not a file URL: {file_url}")

    path = url2pathname(unquote(parsed.path))
    if parsed.netloc and parsed.netloc != "localhost":
        # UNC path, e.g. file://server/share/folder
        path = f"\\\\{parsed.netloc}{path}"
    return Path(path).resolve()
