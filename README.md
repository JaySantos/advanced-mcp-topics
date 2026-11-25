# MCP Chat with File System Access

MCP Chat is a command-line interface application that enables interactive chat capabilities with AI models through the Anthropic API. The application supports file system operations with controlled access to specified directories, video conversion capabilities, and extensible tool integrations via the MCP (Model Control Protocol) architecture.

## Prerequisites

- Python 3.10+
- Anthropic API Key
- FFmpeg (for video conversion features)

## Setup

_You must have FFmpeg already installed to convert a video file_. To install FFmpeg on MacOS run:

```
brew install ffmpeg
```

### Step 1: Configure the environment variables

1. Copy the `.env.example` file to create a new `.env` file:

```bash
cp .env.example .env
```

2. Edit the `.env` file and set your environment variables:

```
CLAUDE_MODEL="claude-sonnet-4-0"  # Or your preferred Claude model
ANTHROPIC_API_KEY=""  # Enter your Anthropic API secret key
```

### Step 2: Install dependencies

#### Setup with uv

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and resolver.

1. Install uv, if not already installed:

```bash
pip install uv
```

2. Install dependencies:

```bash
uv sync
```

3. Run the project

When running the project, you must specify one or more root directories that the MCP server will have access to. Only files and directories within these roots can be accessed by the server.

```bash
uv run main.py <root1> [root2] [root3] ...
```

Examples:

```bash
# Single directory
uv run main.py /path/to/videos

# Multiple directories
uv run main.py /home/user/videos /mnt/storage/media ~/Documents

# Current directory
uv run main.py .
```

## Features

### File System Access

The server can only access files and directories within the specified root paths. This provides security by limiting file system access to approved locations.

### Available Tools

- **list_roots**: List all accessible root directories
- **read_dir**: Read contents of a directory (must be within a root)
- **convert_video**: Convert MP4 videos to other formats (avi, mov, webm, mkv, gif)

### Video Conversion

The video conversion tool uses FFmpeg to convert MP4 files to various formats:

- Standard video formats: AVI, MOV, WebM, MKV
- GIF conversion with optimized settings
- Medium quality preset for balanced file size and quality

## How a request flows (walkthrough)

Example: `uv run main.py XYZ`, where `XYZ` contains `movie.mp4`, then the prompt `convert file movie.mp4 to .mov`.

### Startup

1. **`main.py`** loads `.env.local`, creates `Claude(model=...)`, and takes `root_paths = ["XYZ"]` from the command line.
2. **`MCPClient(... roots=["XYZ"])`**: `_create_roots` resolves `XYZ` to an absolute path and wraps it as a `Root` with the URI `file:///C:/…/XYZ`.
3. **`connect()`** starts the server (`uv run mcp_server.py`) as a subprocess that talks over stdio. It opens a `ClientSession` with `list_roots_callback=_handle_list_roots`, and `initialize()` tells the server that this client supports **roots**.
4. **`CliChat`** and **`CliApp`** are created, and the `> ` prompt appears.

### Timeline

Claude only sees the text `movie.mp4`. It doesn't know which folder the file is in, so it usually looks that up first.

```
 TIME   CLIENT (main.py)                     MCP SERVER (mcp_server.py)         ANTHROPIC API
 ─────  ───────────────────────────────────  ─────────────────────────────────  ─────────────
 0.00s  CliApp.run: prompt_async gets text
        Chat.run(query, stream=True)
          messages = [user: "convert file..."]

 ── Loop iteration 1 ───────────────────────────────────────────────────────────────────────
 0.01s  ToolManager.get_all_tools
          tools/list ───────────────────────▶ returns convert_video, list_roots,
          ◀───────────────────────────────── read_dir (+ JSON input schemas)
 0.05s  claude.chat_stream(messages, tools) ──────────────────────────────────────▶ Claude
 0.8s   streams: tool_use list_roots {}  ◀──────────────────────────────────────────
        CliApp prints 🔧 list_roots box
        stop_reason == "tool_use"
        ToolManager.execute_tool_requests
          tools/call list_roots ───────────▶ list_roots(ctx)
                                              ctx.session.list_roots()
          ◀──── roots/list request ───────── (server → client)
        _handle_list_roots →
          ListRootsResult([file:///C:/…/XYZ]) ─▶
                                              file_url_to_path → "C:\…\XYZ"
          ◀───────── tool result ─────────── ["C:\…\XYZ"]
 0.9s   messages += assistant(tool_use), user(tool_result)

 ── Loop iteration 2 (optional: Claude checks the folder contents) ──────────────────────────
 1.0s   tools/list, chat_stream ──────────────────────────────────────────────────▶ Claude
 1.6s   tool_use read_dir {path:"C:\…\XYZ"} ◀───────────────────────────────────────
          tools/call read_dir ─────────────▶ is_path_allowed → roots/list again
          ◀───── roots/list ─────────────── (client answers again)
                                              XYZ is inside a root ✓
          ◀───────── tool result ─────────── ["movie.mp4"]

 ── Loop iteration 3 ───────────────────────────────────────────────────────────────────────
 1.8s   tools/list, chat_stream ──────────────────────────────────────────────────▶ Claude
 2.4s   tool_use convert_video ◀──────────────────────────────────────────────────────
          {input_path:"C:\…\XYZ\movie.mp4", format:"mov"}
          tools/call convert_video ────────▶ VideoConverter.validate_input
                                                exists? ends with .mp4? ✓
                                              is_path_allowed
          ◀───── roots/list ─────────────── (client answers again)
                                                parent folder XYZ is inside a root ✓
                                              VideoConverter.convert
                                                output = "C:\…\XYZ\movie.mov"
                                                spawns: ffmpeg -i movie.mp4 -y
                                                  -c:v libx264 -preset medium
                                                  -crf 23 -c:a aac -b:a 128k movie.mov
   …    (client waits; this is the slow part)  ffmpeg re-encodes the video
 ~Ns    ◀───────── tool result ─────────── "Successfully converted … to …movie.mov"

 ── Loop iteration 4 ───────────────────────────────────────────────────────────────────────
 ~N+.1  tools/list, chat_stream ──────────────────────────────────────────────────▶ Claude
 ~N+1   streams "Done! movie.mov is in XYZ" ◀───────────────────────────────────────
        stop_reason == "end_turn" → loop breaks, "> " prompt returns
```

Times are approximate and only show the order of events.

### How the pieces fit

- **`Chat.run`'s `while True` loop** (`core/chat.py`) drives the conversation. Each pass asks Claude what to do next, runs any tools it requests, and adds the results to `messages`. The loop ends when Claude stops asking for tools.
- **Claude never touches files.** It only chooses tools and their arguments. The server checks paths and runs ffmpeg.
- **Roots are a permission boundary.** The client decides which folders are allowed. The server asks the client for that list (`roots/list`) on every check in `is_path_allowed`, so it never relies on an old copy.
- **There are three processes:** the client (`main.py`), the server (`mcp_server.py`), and `ffmpeg`, which the server starts.

### Where it can go wrong

- **A relative path skips the root check.** If Claude passes just `"movie.mp4"`, `validate_input` looks for it in the **server's** working folder, not in `XYZ`. It fails with "Input file not found", and Claude usually retries with the full path.
- **Only the input file is checked.** The output file is written next to the input, but nothing checks the output path separately.
- **Extra `tools/list` calls.** `get_all_tools` runs on every loop pass, and `_find_client_with_tool` runs `tools/list` again for each tool call. That's harmless but adds a few round trips.
- **The client can't tell ffmpeg is working.** `convert` sends no progress updates, so on a long video the CLI looks frozen until the result comes back.
