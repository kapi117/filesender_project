# FileSender Matrix

A command-line and web-based application for transferring files between computers on the same local network.

## Features

* **Discoverable Servers**: Servers running `filesender` can be discovered by other instances on the network.
* **Direct File Transfer**: Send files directly to a chosen recipient.
* **Recipient Confirmation**: The recipient is prompted to accept or reject incoming files (via CLI or Web UI).
* **Cross-Platform**: Python backend, Web UI.
* **CLI and Web Interface**: Choose between a command-line interface or a user-friendly web interface.

## Prerequisites

* Python 3.7+
* Node.js and npm (for the web frontend)
* Computers must be on the same local network.

## Setup

1. **Clone/Download the project.**
2. **Install Python dependencies:**

    ```bash
    pip install Flask Flask-CORS
    ```

3. **Setup the Frontend:**

    ```bash
    cd frontend
    npm install
    npm run build
    cd ..
    ```

    This will install frontend dependencies and create an optimized build in the `frontend/build` directory.

## Usage

The application can be run with a Web UI (recommended for ease of use) or via the traditional CLI.

### Web Interface (Recommended)

1. **Start the application server:**
    Open a terminal in the project root directory and run:

    ```bash
    python filesender.py
    ```

    Or explicitly:

    ```bash
    python filesender.py gui
    ```

    This will start the Flask backend server (defaulting to port 5000). It will print the URL to access the web interface (e.g., `http://<your-local-ip>:5000`).

2. **Open the Web UI in your browser:**
    Navigate to the URL provided in the terminal.

3. **Using the Web UI:**
    * **Server Control**: Start/Stop the underlying FileSender server. The server must be running to send/receive files or discover devices.
    * **Incoming Transfers**: If the server is running and a file is sent to your machine, a prompt will appear in this section allowing you to accept or reject it.
    * **Discover Devices**: Click "Search Network" to find other FileSender instances (both CLI and GUI servers) on your network. Select a device from the list to set it as the target for sending a file.
    * **Send File**: Drag and drop a file into the designated area or click to browse. Ensure a target host is selected from the discovered devices list or typed in. Click "Send File".
    * **Activity Log**: Shows recent actions and messages from the application.

### Command-Line Interface (CLI)

The CLI still functions as before and uses the same core logic.

1. **Start the Server (CLI mode):**
    On the computer that will receive files, open a terminal in the project directory and run:

    ```bash
    python filesender.py start
    ```

    The server will start. Incoming file requests will prompt for confirmation in the terminal.

2. **Search for Servers (CLI mode):**

    ```bash
    python filesender.py search
    ```

    This lists available FileSender servers on the network.

3. **Send a File (CLI mode):**

    ```bash
    python filesender.py send [filepath] [hostname_or_ip]
    ```

    Example:

    ```bash
    python filesender.py send ./mydoc.txt server-laptop
    ```

    The recipient (if running in CLI mode) will be prompted in their terminal. If the recipient is using the Web UI, the confirmation will appear there.

## Configuration

* **Backend**: Network settings (ports, discovery message) are defined at the top of `filesender_core.py`.
* **Frontend**: The React app proxies API requests to `http://localhost:5000` during development (see `frontend/package.json`). The Flask server port can be changed when running `python filesender.py gui --port <your_port>`.

## Firewall Configuration

For `filesender` to work correctly, your system's firewall must allow traffic on the configured UDP and TCP ports (defaults are UDP 60001 and TCP 60000):

* **UDP Port (e.g., 60001)**: Must be open for incoming and outgoing traffic for device discovery.
* **TCP Port (e.g., 60000)**: Must be open for incoming traffic on the server machine to receive files, and outgoing on the client machine to send files.

## Troubleshooting

* **Web UI not loading**: Ensure you have run `npm run build` in the `frontend` directory and that the Flask server is running.
* **No servers found (Web UI or CLI)**:
  * Ensure the FileSender server is running on target machines (either `python filesender.py` for GUI-managed server, or `python filesender.py start` for CLI server).
  * Check that all devices are on the same local network.
  * Verify firewall settings on all machines.
* **Connection refused when sending**:
  * Verify server is active on the target machine.
  * Double-check hostname/IP.
  * Check firewalls.

Received files (accepted via CLI or UI) are saved in a `received_files` directory in the project root (where `filesender.py` is run).
