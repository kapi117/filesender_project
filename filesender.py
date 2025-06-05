import argparse
import socket
import threading
import os
import time

from config import TCP_PORT, UDP_PORT, DISCOVERY_MESSAGE, BUFFER_SIZE


def get_local_ip():
    """Gets the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


def start_server():
    """Starts the server to listen for discovery messages and incoming files."""
    local_ip = get_local_ip()
    print(f"Server starting on {local_ip}...")

    # Thread for UDP Discovery
    discovery_thread = threading.Thread(
        target=listen_for_discovery, args=(local_ip,), daemon=True
    )
    discovery_thread.start()

    # Thread for TCP File Reception
    file_reception_thread = threading.Thread(
        target=listen_for_files, args=(local_ip,), daemon=True
    )
    file_reception_thread.start()

    print(f"Server is running. Visible as '{socket.gethostname()}' ({local_ip}).")
    print("Listening for file transfers and discovery requests. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServer shutting down...")


def listen_for_discovery(local_ip):
    """Listens for UDP discovery broadcasts and responds."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        udp_socket.bind(("", UDP_PORT))
        print(f"Discovery service listening on UDP port {UDP_PORT}")
    except socket.error as e:
        print(f"Error binding UDP socket for discovery: {e}")
        print("Is another instance already running or the port in use?")
        return

    while True:
        try:
            data, addr = udp_socket.recvfrom(BUFFER_SIZE)
            message = data.decode()
            if message == DISCOVERY_MESSAGE:
                print(f"Discovery request from {addr[0]}. Responding...")
                response = f"{socket.gethostname()};{local_ip}"
                udp_socket.sendto(response.encode(), addr)
        except Exception as e:
            print(f"Error in discovery listener: {e}")
            time.sleep(1)  # Avoid busy-looping on error


def listen_for_files(local_ip):
    """Listens for incoming TCP connections for file transfer."""
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        tcp_socket.bind((local_ip, TCP_PORT))
        tcp_socket.listen(5)
        print(f"File transfer service listening on TCP port {TCP_PORT}")
    except socket.error as e:
        print(f"Error binding TCP socket for file transfer: {e}")
        print("Is another instance already running or the port in use?")
        return

    while True:
        try:
            conn, addr = tcp_socket.accept()
            print(f"Incoming connection from {addr[0]} for file transfer.")
            # Handle each client connection in a new thread
            threading.Thread(
                target=handle_file_reception, args=(conn, addr), daemon=True
            ).start()
        except Exception as e:
            print(f"Error accepting connection: {e}")
            time.sleep(1)


def handle_file_reception(conn, addr):
    """Handles a single file reception connection."""
    try:
        # 1. Receive file info (filename, filesize)
        file_info_str = conn.recv(BUFFER_SIZE).decode()
        if not file_info_str:
            print(f"No file info received from {addr[0]}. Closing connection.")
            return

        filename, filesize_str = file_info_str.split(";")
        filesize = int(filesize_str)
        print(f"Receiving file: {filename} ({filesize} bytes) from {addr[0]}")

        # Sanitize filename to prevent directory traversal
        filename = os.path.basename(filename)
        if not filename:  # Handle cases like ".." or "/"
            print(f"Invalid filename '{filename}' received from {addr[0]}. Rejecting.")
            conn.sendall(b"REJECTED_INVALID_FILENAME")
            return

        # 2. Ask user for confirmation
        user_confirmation = input(
            f"Accept '{filename}' ({filesize} bytes) from {addr[0]}? (yes/no): "
        ).lower()
        if user_confirmation == "yes":
            conn.sendall(b"OK")
        else:
            conn.sendall(b"REJECTED")
            print(f"Rejected file {filename} from {addr[0]}.")
            return

        # 3. Receive file data
        received_bytes = 0
        # Ensure 'received_files' directory exists
        os.makedirs("received_files", exist_ok=True)
        file_path = os.path.join("received_files", filename)

        with open(file_path, "wb") as f:
            while received_bytes < filesize:
                chunk = conn.recv(BUFFER_SIZE)
                if not chunk:
                    break  # Connection closed prematurely
                f.write(chunk)
                received_bytes += len(chunk)
                # Optional: print progress
                # print(f"\rReceived {received_bytes}/{filesize} bytes...", end="")

        if received_bytes == filesize:
            print(
                f"\nFile '{filename}' received successfully and saved to '{file_path}'."
            )
            conn.sendall(b"SUCCESS")
        else:
            print(
                f"\nFile transfer for '{filename}' incomplete. Expected {filesize}, got {received_bytes}."
            )
            conn.sendall(b"FAILED")
            if os.path.exists(file_path):  # Clean up partial file
                os.remove(file_path)

    except Exception as e:
        print(f"Error during file reception from {addr[0]}: {e}")
        try:
            conn.sendall(b"ERROR")  # Notify sender of a server-side error
        except socket.error:
            pass  # Connection might already be closed
    finally:
        conn.close()
        print(f"Connection with {addr[0]} closed.")


def search_servers():
    """Searches for available servers on the network."""
    print("Searching for servers...")
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.settimeout(5)  # Wait 5 seconds for responses

    found_servers = {}  # To store unique servers: ip -> hostname

    try:
        # Send broadcast message
        # For some networks, '<broadcast>' might not work, and a specific subnet broadcast (e.g., '192.168.1.255') is needed.
        # Using '255.255.255.255' is generally more robust for local networks if allowed.
        # If issues persist, this might need to be configured or determined dynamically.
        broadcast_address = "<broadcast>"  # Or '255.255.255.255'
        udp_socket.sendto(DISCOVERY_MESSAGE.encode(), (broadcast_address, UDP_PORT))
        print(f"Discovery message sent to {broadcast_address}:{UDP_PORT}")

        while True:
            try:
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
                response = data.decode()
                hostname, ip_address = response.split(";")
                if ip_address not in found_servers:
                    found_servers[ip_address] = hostname
                    print(f"Found server: {hostname} ({ip_address})")
            except socket.timeout:
                break  # No more responses
            except Exception as e:
                print(f"Error receiving discovery response: {e}")
                continue
    except socket.error as e:
        print(f"Socket error during search: {e}. Ensure network allows broadcasts.")
    finally:
        udp_socket.close()

    if not found_servers:
        print("No servers found.")
    else:
        print("\nAvailable servers:")
        for ip, host in found_servers.items():
            print(f"  - {host} (IP: {ip})")


def send_file(filepath, target_host):
    """Sends a file to the specified host."""
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        return
    if not os.path.isfile(filepath):
        print(f"Error: '{filepath}' is not a file.")
        return

    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)

    print(f"Preparing to send '{filename}' ({filesize} bytes) to {target_host}...")

    try:
        # Resolve hostname if it's not an IP
        try:
            target_ip = socket.gethostbyname(target_host)
        except socket.gaierror:
            print(
                f"Error: Could not resolve hostname '{target_host}'. Is it a valid IP or hostname?"
            )
            return

        print(f"Connecting to {target_host} ({target_ip}) on port {TCP_PORT}...")
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.settimeout(10)  # 10 seconds to connect

        try:
            tcp_socket.connect((target_ip, TCP_PORT))
        except socket.timeout:
            print(f"Connection to {target_host} timed out.")
            return
        except socket.error as e:
            print(f"Connection to {target_host} failed: {e}")
            return

        print("Connected. Sending file information...")
        # 1. Send file info (filename;filesize)
        file_info = f"{filename};{filesize}"
        tcp_socket.sendall(file_info.encode())

        # 2. Wait for server confirmation
        print("Waiting for recipient to accept...")
        confirmation = tcp_socket.recv(BUFFER_SIZE).decode()

        if confirmation == "OK":
            print("Recipient accepted. Sending file...")
            sent_bytes = 0
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(BUFFER_SIZE)
                    if not chunk:
                        break  # End of file
                    tcp_socket.sendall(chunk)
                    sent_bytes += len(chunk)
                    # Optional: print progress
                    # print(f"\rSent {sent_bytes}/{filesize} bytes...", end="")

            print("\nFile sent. Waiting for final confirmation...")
            final_status = tcp_socket.recv(BUFFER_SIZE).decode()
            if final_status == "SUCCESS":
                print(f"File '{filename}' sent successfully to {target_host}.")
            elif final_status == "FAILED":
                print(f"Recipient reported an error receiving the file.")
            else:
                print(f"Received unexpected final status: {final_status}")

        elif confirmation == "REJECTED":
            print(f"Recipient rejected the file '{filename}'.")
        elif confirmation == "REJECTED_INVALID_FILENAME":
            print(
                f"Recipient rejected the file due to an invalid filename. Please rename the file."
            )
        else:
            print(f"Received unexpected response from server: {confirmation}")

    except socket.timeout:
        print(f"A timeout occurred while communicating with {target_host}.")
    except socket.error as e:
        print(f"Socket error during send: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if "tcp_socket" in locals() and tcp_socket.fileno() != -1:
            tcp_socket.close()
        print("Send operation finished.")


def main():
    parser = argparse.ArgumentParser(
        description="FileSender: Transfer files over the local network."
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )

    # Start command
    parser_start = subparsers.add_parser(
        "start", help="Launches a server on this computer."
    )
    parser_start.set_defaults(func=start_server)

    # Search command
    parser_search = subparsers.add_parser(
        "search", help="Searches for other devices with the server running."
    )
    parser_search.set_defaults(func=search_servers)

    # Send command
    parser_send = subparsers.add_parser(
        "send", help="Sends a file to a specified host."
    )
    parser_send.add_argument("filename", type=str, help="The path to the file to send.")
    parser_send.add_argument(
        "hostname", type=str, help="The hostname or IP address of the recipient."
    )
    parser_send.set_defaults(func=lambda args: send_file(args.filename, args.hostname))

    args = parser.parse_args()

    if hasattr(args, "func"):
        if args.command == "send":
            args.func(args)  # Pass the full args namespace for send
        else:
            args.func()  # Call start_server or search_servers directly
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
