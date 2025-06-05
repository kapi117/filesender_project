import argparse
import sys
import threading
import time
from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS
import os

from filesender_core import FileSenderCore

# from config import TCP_PORT, UDP_PORT # Core handles its own config now

# --- Global Core Instance --- #
# For GUI mode, confirmation is handled via Flask endpoints
# For CLI mode, confirmation is handled via input()
core = FileSenderCore(confirmation_mode="gui")

# --- Flask App --- #
app = Flask(__name__, static_folder="frontend/build")
CORS(app)  # Allow all origins for simplicity in development


# --- API Endpoints --- #
@app.route("/api/server/status", methods=["GET"])
def get_server_status():
    return jsonify(core.get_server_status())


@app.route("/api/server/start", methods=["POST"])
def start_server_api():
    if core.server_running:
        return jsonify({"success": False, "message": "Server already running."}), 400
    success = core.start_server()
    if success:
        return jsonify(
            {"success": True, "message": "Server started."} | core.get_server_status()
        )
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Failed to start server. Check console for errors.",
                }
                | core.get_server_status()
            ),
            500,
        )


@app.route("/api/server/stop", methods=["POST"])
def stop_server_api():
    if not core.server_running:
        return jsonify({"success": False, "message": "Server not running."}), 400
    core.stop_server()
    return jsonify(
        {"success": True, "message": "Server stopped."} | core.get_server_status()
    )


@app.route("/api/devices/search", methods=["GET"])
def search_devices_api():
    devices = core.search_devices()
    return jsonify(devices)


@app.route("/api/file/send", methods=["POST"])
def send_file_api():
    if "file" not in request.files:
        return (
            jsonify({"success": False, "message": "No file part in the request."}),
            400,
        )
    file = request.files["file"]
    target_host = request.form.get("hostname")

    if not target_host:
        return jsonify({"success": False, "message": "No hostname provided."}), 400
    if file.filename == "":
        return jsonify({"success": False, "message": "No selected file."}), 400

    # Save the uploaded file temporarily to send it using the core logic
    # which expects a filepath
    temp_dir = "_temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    temp_filepath = os.path.join(temp_dir, file.filename)
    try:
        file.save(temp_filepath)
        result = core.send_file(temp_filepath, target_host)
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)  # Clean up temp file
        # Consider removing temp_dir if empty, but be careful with concurrent requests

    return jsonify(result)


@app.route("/api/file/confirmations", methods=["GET"])
def get_pending_confirmations_api():
    confirmations = core.get_pending_confirmations()
    return jsonify(confirmations)


@app.route("/api/file/respond", methods=["POST"])
def respond_to_confirmation_api():
    data = request.get_json()
    transfer_id = data.get("id")
    decision = data.get("decision")  # 'accept' or 'reject'

    if not transfer_id or decision not in ["accept", "reject"]:
        return (
            jsonify(
                {"success": False, "message": "Invalid request. Need id and decision."}
            ),
            400,
        )

    success = core.respond_to_confirmation(transfer_id, decision)
    if success:
        return jsonify(
            {"success": True, "message": f"Responded '{decision}' to {transfer_id}."}
        )
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Failed to respond to {transfer_id}. It might have timed out or already been handled.",
                }
            ),
            404,
        )


# --- Serve React App --- #
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react_app(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    elif path.startswith("api/"):  # Don't let React routing interfere with API calls
        return abort(404)
    else:
        return send_from_directory(app.static_folder, "index.html")


# --- CLI Functions (using the same core) --- #
def cli_start_server():
    # For CLI, switch core to CLI confirmation mode temporarily if it was in GUI mode
    original_mode = core.confirmation_mode
    core.confirmation_mode = "cli"
    print("CLI: Starting server...")
    if not core.start_server():
        print(
            "CLI: Failed to start server. It might be already running or port in use."
        )
        core.confirmation_mode = original_mode
        return

    status = core.get_server_status()
    print(
        f"CLI: Server is running. Visible as '{status['hostname']}' ({status['ip']})."
    )
    print(
        "CLI: Listening for file transfers and discovery requests. Press Ctrl+C to stop."
    )
    try:
        while core.server_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCLI: Server shutting down...")
    finally:
        core.stop_server()
        core.confirmation_mode = original_mode
        print("CLI: Server stopped.")


def cli_search_servers():
    print("CLI: Searching for servers...")
    servers = core.search_devices(timeout=5)
    if not servers:
        print("CLI: No servers found.")
    else:
        print("CLI: Available servers:")
        for server in servers:
            app_info = f" (App: {server['app']})" if server["app"] else ""
            print(f"  - {server['hostname']} (IP: {server['ip']}){app_info}")


def cli_send_file(filepath, target_host):
    print(f"CLI: Preparing to send '{filepath}' to {target_host}...")
    result = core.send_file(filepath, target_host)
    print(f"CLI: {result['message']}")


# --- Main Application Runner --- #
def main():
    parser = argparse.ArgumentParser(
        description="FileSenderMatrix: Transfer files with CLI or Web UI."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # GUI command (default if no command is given)
    parser_gui = subparsers.add_parser(
        "gui", help="Starts the Flask server for the Web UI."
    )
    parser_gui.add_argument(
        "--port", type=int, default=5000, help="Port for the Flask web server."
    )
    parser_gui.set_defaults(
        func=lambda args: app.run(host="0.0.0.0", port=args.port, debug=False)
    )

    # CLI Start command
    parser_start = subparsers.add_parser(
        "start", help="Launches a server on this computer (CLI mode)."
    )
    parser_start.set_defaults(func=lambda args: cli_start_server())

    # CLI Search command
    parser_search = subparsers.add_parser(
        "search", help="Searches for other devices (CLI mode)."
    )
    parser_search.set_defaults(func=lambda args: cli_search_servers())

    # CLI Send command
    parser_send = subparsers.add_parser(
        "send", help="Sends a file to a specified host (CLI mode)."
    )
    parser_send.add_argument("filename", type=str, help="The path to the file to send.")
    parser_send.add_argument(
        "hostname", type=str, help="The hostname or IP address of the recipient."
    )
    parser_send.set_defaults(
        func=lambda args: cli_send_file(args.filename, args.hostname)
    )

    # If no command is specified, default to 'gui'
    if len(sys.argv) == 1:
        args = parser.parse_args(["gui"])
    else:
        args = parser.parse_args()

    if hasattr(args, "func"):
        # For GUI, Flask runs in the main thread. For CLI, core operations might use threads.
        if args.command == "gui":
            print(
                f"Starting FileSenderMatrix Web UI on http://{core.local_ip}:{args.port} or http://127.0.0.1:{args.port}"
            )
            print(
                "Note: The FileSenderCore server (for discovery/transfer) will start on demand via API calls."
            )
            args.func(args)
        else:
            # CLI commands run directly. Ensure core is in CLI mode for confirmations.
            original_mode = core.confirmation_mode
            core.confirmation_mode = "cli"
            args.func(args)
            core.confirmation_mode = original_mode  # Restore mode if it was GUI
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
