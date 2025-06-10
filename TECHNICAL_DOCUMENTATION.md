# FileSender Technical Documentation

## 1. Introduction

FileSender is a Python-based application designed for transferring files between devices on a local network. It utilizes a combination of UDP for device discovery and TCP for reliable file transmission. The application can be operated via a command-line interface (CLI) or a web-based graphical user interface (GUI) powered by Flask and React.

## 2. Core Components and Mechanisms

The project is primarily structured around three Python files: `config.py`, `filesender_core.py`, and `filesender.py`.

### 2.1. `config.py`

This file centralizes configuration parameters used throughout the application.

- **`TCP_PORT` (default: 60000):** The network port used for TCP connections, primarily for file data transfer.
- **`UDP_PORT` (default: 60001):** The network port used for UDP broadcast and unicast messages, primarily for device discovery.
- **`DISCOVERY_MESSAGE` (default: "FILESENDER_DISCOVERY"):** A specific string message used in UDP broadcasts to identify other FileSender instances on the network.
- **`BUFFER_SIZE` (default: 4096):** The size (in bytes) of the data chunks read from files and sent over the network. This affects network performance and memory usage during transfers.
- **`APP_NAME` (default: "FileSenderMatrix"):** An identifier for the application, used in discovery responses.

### 2.2. `filesender_core.py`

This module encapsulates the fundamental logic for device discovery, file sending, and file receiving. It is designed to be independent of the user interface (CLI or GUI).

#### 2.2.1. `FileSenderCore` Class

This is the main class managing the core functionalities.

- **Initialization (`__init__`)**:
    - Determines the local IP address using `get_local_ip()`.
    - Gets the local machine's hostname.
    - Initializes threading events (`stop_event`) for graceful shutdown of server components.
    - Sets the `confirmation_mode` ("cli" or "gui") which dictates how incoming file transfer requests are confirmed by the user.
    - Manages a list for pending GUI confirmations (`pending_gui_confirmations`) and a lock (`gui_confirmation_lock`) for thread-safe access.

- **Device Discovery**:
    - **`_listen_for_discovery_task()`**:
        - Runs in a separate thread.
        - Creates a UDP socket bound to `UDP_PORT` to listen for incoming discovery messages.
        - When a `DISCOVERY_MESSAGE` is received, it responds with the sender's hostname, IP address, and `APP_NAME`.
        - Uses `socket.SO_REUSEADDR` to allow quick restarts of the listener.
        - Has a timeout to periodically check the `stop_event`.
    - **`search_devices(timeout=3)`**:
        - Creates a UDP socket and enables broadcasting (`socket.SO_BROADCAST`).
        - Sends the `DISCOVERY_MESSAGE` to the broadcast address (`<broadcast>`) on `UDP_PORT`.
        - Listens for responses for a specified `timeout` duration.
        - Collects unique responses (hostname, IP, app name) from other FileSender instances.
        - Filters responses to include only those from `APP_NAME` or older clients (empty app name).

- **File Reception**:
    - **`_listen_for_files_task()`**:
        - Runs in a separate thread.
        - Creates a TCP server socket bound to the local IP and `TCP_PORT`.
        - Listens for incoming TCP connections (file transfer requests).
        - When a connection is accepted, it spawns a new thread (`_handle_file_reception_task`) to manage that specific transfer, allowing concurrent receptions.
        - Uses `socket.SO_REUSEADDR`.
        - Has a timeout to periodically check the `stop_event`.
    - **`_handle_file_reception_task(conn, addr)`**:
        - Manages an individual file reception.
        - Receives file metadata (filename, filesize) from the sender.
        - **Confirmation Handling**:
            - If `confirmation_mode` is "cli", it prompts the user via `input()` to accept or reject the file.
            - If `confirmation_mode` is "gui", it creates a pending confirmation entry (with a unique `transfer_id`, filename, size, sender address, and a `Queue` for the response). This entry is then made available to the GUI via an API endpoint. The thread waits for a response on the queue (e.g., from a GUI interaction) with a timeout.
        - If accepted:
            - Sends an "OK" confirmation to the sender.
            - Creates a "received_files" directory if it doesn't exist.
            - Opens the file in binary write mode (`"wb"`).
            - Receives file data in chunks (`BUFFER_SIZE`) and writes them to the file.
            - Sends "SUCCESS" or "FAILED" to the sender based on whether all bytes were received.
            - Cleans up the partially received file on failure.
        - If rejected or an error occurs:
            - Sends "REJECTED" or "ERROR_TRANSFER" to the sender.
            - Closes the connection.

- **File Sending**:
    - **`send_file(filepath, target_host)`**:
        - Validates the `filepath`.
        - Resolves the `target_host` (hostname or IP) to an IP address.
        - Creates a TCP client socket.
        - Connects to the target host on `TCP_PORT`.
        - Sends file metadata (filename, filesize).
        - Waits for an "OK" confirmation from the receiver.
        - If "OK" is received:
            - Reads the file in chunks (`BUFFER_SIZE`) and sends them.
            - Waits for a final status ("SUCCESS" or "FAILED") from the receiver.
        - Returns a dictionary indicating success or failure and a message.

- **Server Management**:
    - **`start_server()`**:
        - Clears the `stop_event`.
        - Starts the `_listen_for_discovery_task` and `_listen_for_files_task` threads.
        - Sets `server_running` to `True`.
        - Includes a check to ensure the file listener socket successfully binds.
    - **`stop_server()`**:
        - Sets the `stop_event` to signal threads to terminate.
        - Joins the discovery and file listener threads to wait for their completion.
        - Closes the file listener socket if it's still open.
        - Sets `server_running` to `False`.
    - **`get_server_status()`**: Returns a dictionary with the server's running state, local IP, and hostname.

- **GUI Confirmation Helpers**:
    - **`_get_next_confirmation_id()`**: Generates unique IDs for GUI transfer confirmations.
    - **`get_pending_confirmations()` (called by Flask API in `filesender.py`)**: Returns a list of pending file transfer requests for the GUI.
    - **`respond_to_confirmation(transfer_id, decision)` (called by Flask API in `filesender.py`)**: Allows the GUI to accept or reject a pending transfer by putting the decision onto the corresponding response queue in `_handle_file_reception_task`.

- **Helper Functions**:
    - **`get_local_ip()`**: A utility to find the machine's local IP address by attempting to connect to an external address (doesn't actually send data). Defaults to "127.0.0.1" if an external connection cannot be established.

### 2.3. `filesender.py`

This file serves as the main entry point for the application. It integrates the `FileSenderCore` with a Flask web server for the GUI and an `argparse`-based command-line interface.

#### 2.3.1. Global `FileSenderCore` Instance

A single instance of `FileSenderCore` is created with `confirmation_mode="gui"` by default. This mode is temporarily switched to "cli" when CLI commands are executed.

#### 2.3.2. Flask Web Application (`app`)

- **Initialization**:
    - A Flask app is created, configured to serve static files from `frontend/build` (where the React frontend is expected to be).
    - `Flask-CORS` is enabled to allow cross-origin requests, typically needed during development when the frontend and backend might be served on different ports.

- **API Endpoints (prefixed with `/api`)**:
    - **`/api/server/status` (GET)**: Returns the current status of the core server (running state, IP, hostname) by calling `core.get_server_status()`.
    - **`/api/server/start` (POST)**: Starts the core server by calling `core.start_server()`. Returns success/failure and current status.
    - **`/api/server/stop` (POST)**: Stops the core server by calling `core.stop_server()`. Returns success/failure and current status.
    - **`/api/devices/search` (GET)**: Searches for other FileSender devices on the network by calling `core.search_devices()`. Returns a list of found devices.
    - **`/api/file/send` (POST)**:
        - Expects a multipart form request with a 'file' part and a 'hostname' form field.
        - Saves the uploaded file temporarily to a `_temp_uploads` directory because `core.send_file()` expects a filepath.
        - Calls `core.send_file()` with the temporary filepath and target hostname.
        - Deletes the temporary file after the operation.
        - Returns the result from `core.send_file()`.
    - **`/api/file/confirmations` (GET)**: Retrieves the list of pending file transfer confirmations from `core.get_pending_confirmations()` for the GUI to display.
    - **`/api/file/respond` (POST)**:
        - Expects JSON data with `id` (transfer_id) and `decision` ("accept" or "reject").
        - Calls `core.respond_to_confirmation()` to process the GUI's decision for a pending transfer.
        - Returns success or failure.

- **Serving React Frontend**:
    - **`@app.route("/", defaults={"path": ""})`**
    - **`@app.route("/<path:path>")`**:
        - These routes are configured to serve the React application.
        - If the requested path exists in the `static_folder` (`frontend/build`), it serves that static file (e.g., CSS, JS, images).
        - If the path starts with `api/`, it aborts with a 404 to prevent React routing from interfering with API calls.
        - Otherwise, it serves `index.html` from the `static_folder`, allowing React Router to handle client-side navigation.

#### 2.3.3. Command-Line Interface (CLI) Functions

These functions wrap `FileSenderCore` methods for CLI usage.

- **`cli_start_server()`**:
    - Temporarily sets `core.confirmation_mode` to "cli".
    - Calls `core.start_server()`.
    - Prints server status and instructions.
    - Waits for `KeyboardInterrupt` (Ctrl+C) to stop the server.
    - Calls `core.stop_server()` and restores the original confirmation mode.
- **`cli_search_servers()`**: Calls `core.search_devices()` and prints the found servers.
- **`cli_send_file(filepath, target_host)`**: Calls `core.send_file()` and prints the result.

#### 2.3.4. Main Application Runner (`main()`)

- **Argument Parsing (`argparse`)**:
    - Sets up command-line arguments for different modes of operation:
        - **`gui` (default)**: Starts the Flask web server. Takes an optional `--port` argument.
        - **`start`**: Runs `cli_start_server()`.
        - **`search`**: Runs `cli_search_servers()`.
        - **`send`**: Runs `cli_send_file()`. Requires `filename` and `hostname` arguments.
- **Command Execution**:
    - Parses the command-line arguments.
    - If no command is given, it defaults to `gui`.
    - Calls the appropriate function based on the parsed command.
    - For CLI commands, it ensures `core.confirmation_mode` is set to "cli" before execution and restored afterward.
    - For the `gui` command, it starts the Flask development server (`app.run()`).

## 3. Network Communication

### 3.1. UDP for Discovery

- **Broadcast**: To find other devices, a FileSender instance sends a UDP broadcast packet containing `DISCOVERY_MESSAGE` to port `UDP_PORT`. All devices on the same subnet will receive this.
- **Unicast Response**: Devices receiving the discovery message respond directly (unicast) to the sender's IP address (obtained from the incoming packet) on `UDP_PORT` with their hostname, IP, and app name.

### 3.2. TCP for File Transfer

- **Connection Setup**: The sender initiates a TCP connection to the receiver's IP address on `TCP_PORT`.
- **Metadata Exchange**: The sender first sends a string containing `filename;filesize`.
- **Confirmation**: The receiver, after potentially prompting the user, sends back "OK" or "REJECTED".
- **Data Transmission**: If "OK", the sender transmits the file content in chunks. The receiver writes these chunks to a local file.
- **Final Status**: After all data is sent (or an error occurs), the receiver sends "SUCCESS" or "FAILED" (or "ERROR_TRANSFER") to the sender.

## 4. Threading Model

- **`FileSenderCore`**:
    - `_listen_for_discovery_task`: Runs in a dedicated daemon thread to continuously listen for UDP discovery pings.
    - `_listen_for_files_task`: Runs in a dedicated non-daemon thread to continuously listen for incoming TCP file transfer connections.
    - `_handle_file_reception_task`: Each accepted TCP connection for file reception is handled in its own new non-daemon thread. This allows multiple files to be received concurrently.
- **`filesender.py` (CLI mode)**:
    - The `cli_start_server` function blocks the main thread while the core server threads (discovery, file listener) run in the background.
- **`filesender.py` (GUI mode)**:
    - The Flask application runs in the main thread.
    - When API calls trigger `core.start_server()`, the core's threads are started as described above. These threads run concurrently with the Flask request-handling threads.

## 5. Frontend (`frontend/` directory)

The documentation provided focuses on the backend. The `frontend/` directory suggests a JavaScript-based frontend, likely using React, as indicated by `package.json`, `App.js`, and `index.js`.

- **`package.json`**: Defines project metadata, dependencies (e.g., React, ReactDOM), and scripts (e.g., `start`, `build`).
- **`public/index.html`**: The main HTML file that serves as the entry point for the React application.
- **`src/`**: Contains the React component source code.
    - `App.js`: Likely the root component of the React application.
    - `index.js`: The JavaScript entry point that renders the React application into the DOM.
    - `App.css`, `index.css`: CSS files for styling the application.

The Flask backend serves the built React application (expected in `frontend/build`) as static files. The React frontend interacts with the Python backend via the HTTP API endpoints defined in `filesender.py`.

## 6. Workflow Examples

### 6.1. Sending a File (GUI to GUI)

1.  **User A (Sender)** opens the web UI.
2.  The UI calls `/api/server/start` to ensure User A's core server is running (for discovery responses and potential incoming files).
3.  User A uses the UI to search for devices. The UI calls `/api/devices/search`.
    -   User A's `FileSenderCore` broadcasts a UDP `DISCOVERY_MESSAGE`.
4.  **User B (Receiver)** has their FileSender app running (either GUI with server started, or CLI server).
    -   User B's `FileSenderCore` receives the UDP broadcast and responds with its details.
5.  User A's UI displays User B as an available device.
6.  User A selects a file and User B as the target, then clicks "Send".
    -   The UI POSTs the file and target hostname to `/api/file/send`.
    -   `filesender.py` saves the file temporarily.
    -   `core.send_file()` is called. It connects to User B's IP on `TCP_PORT`.
    -   Sends `filename;filesize`.
7.  User B's `_listen_for_files_task` accepts the connection and spawns `_handle_file_reception_task`.
    -   This task receives `filename;filesize`.
    -   Since User B is using the GUI, a pending confirmation is created.
    -   The UI on User B's machine polls `/api/file/confirmations` and displays the incoming file request.
8.  User B clicks "Accept" in their UI.
    -   The UI POSTs `{ "id": "transfer_X", "decision": "accept" }` to `/api/file/respond`.
    -   `core.respond_to_confirmation()` puts "accept" on the queue for the waiting `_handle_file_reception_task`.
9.  User B's `_handle_file_reception_task` receives "accept", sends "OK" back to User A.
    -   It then receives file data and saves it.
    -   Sends "SUCCESS" to User A upon completion.
10. User A's `core.send_file()` receives "OK", sends file data, then receives "SUCCESS".
11. The result is propagated back to User A's UI.

### 6.2. Starting CLI Server

1.  User runs `python filesender.py start`.
2.  `main()` calls `cli_start_server()`.
3.  `core.confirmation_mode` is set to "cli".
4.  `core.start_server()` is called, launching discovery and file listener threads.
5.  The console displays server status. The main thread waits.
6.  If another user sends a file:
    -   `_handle_file_reception_task` is invoked.
    -   It prompts on the console: "Accept 'filename' (size) from IP? (yes/no): ".
    -   User types "yes" or "no".
    -   The transfer proceeds or is rejected accordingly.
7.  User presses Ctrl+C.
8.  `core.stop_server()` is called, shutting down threads.

## 7. Potential Improvements / Considerations

-   **Error Handling**: More granular error reporting to the user, especially for network issues.
-   **Security**:
    -   No encryption is used for file transfers. Data is sent in plaintext.
    -   No authentication beyond the discovery message and app name.
    -   Consider adding options for encryption (e.g., TLS/SSL for TCP).
-   **Scalability**: The current broadcast discovery might not be ideal for very large networks. Multicast DNS (mDNS/Bonjour) could be an alternative.
-   **GUI Robustness**: The temporary file saving in `/api/file/send` could be optimized or made more robust for concurrent requests or large files. Streaming directly from the request to the TCP socket might be possible but complex with the current core structure.
-   **Configuration**: While `config.py` exists, making these settings configurable via the UI or CLI arguments could be beneficial.
-   **Partial Transfers**: Resuming interrupted transfers is not supported.
-   **Directory Transfers**: Only single file transfers are supported.
-   **Dependencies**: Explicitly list Python dependencies (e.g., Flask, Flask-CORS) in a `requirements.txt` file.

This documentation provides a comprehensive overview of the FileSender project's technical mechanisms.
