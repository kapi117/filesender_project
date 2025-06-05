import socket
import threading
import os
import time
from queue import Queue, Empty

# Configuration (can be imported from config.py)
TCP_PORT = 60000
UDP_PORT = 60001
DISCOVERY_MESSAGE = "FILESENDER_DISCOVERY"
BUFFER_SIZE = 4096
APP_NAME = "FileSenderMatrix"


def get_local_ip():
    """Gets the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


class FileSenderCore:
    def __init__(self, confirmation_mode="cli"):
        self.local_ip = get_local_ip()
        self.hostname = socket.gethostname()
        self.server_running = False
        self.stop_event = threading.Event()

        self.discovery_thread = None
        self.file_listener_socket = None
        self.file_listener_thread = None

        self.confirmation_mode = confirmation_mode
        self.pending_gui_confirmations = []
        self.gui_confirmation_lock = threading.Lock()
        self._next_confirmation_id = 0
        self.active_reception_threads = []

    def _get_next_confirmation_id(self):
        with self.gui_confirmation_lock:
            self._next_confirmation_id += 1
            return f"transfer_{self._next_confirmation_id}"

    def _listen_for_discovery_task(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp_socket.bind(("", UDP_PORT))
        except socket.error as e:
            print(f"Core Error (Discovery): {e}")
            return

        udp_socket.settimeout(1.0)
        while not self.stop_event.is_set():
            try:
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
                message = data.decode()
                if message == DISCOVERY_MESSAGE:
                    response = f"{self.hostname};{self.local_ip};{APP_NAME}"
                    udp_socket.sendto(response.encode(), addr)
            except socket.timeout:
                continue
            except Exception:  # Ignore other errors in discovery
                if self.stop_event.is_set():
                    break
                time.sleep(0.1)
        udp_socket.close()

    def _handle_file_reception_task(self, conn, addr):
        transfer_id = None
        try:
            conn.settimeout(20.0)
            file_info_str = conn.recv(BUFFER_SIZE).decode()
            if not file_info_str:
                return

            filename, filesize_str = file_info_str.split(";")
            filesize = int(filesize_str)
            filename = os.path.basename(filename)
            if not filename:
                conn.sendall(b"REJECTED_INVALID_FILENAME")
                return

            decision = "rejected"
            if self.confirmation_mode == "cli":
                user_confirmation = input(
                    f"Accept '{filename}' ({filesize}b) from {addr[0]}? (yes/no): "
                ).lower()
                if user_confirmation == "yes":
                    decision = "accepted"

            elif self.confirmation_mode == "gui":
                response_queue = Queue(1)
                transfer_id = self._get_next_confirmation_id()
                pending_item = {
                    "id": transfer_id,
                    "filename": filename,
                    "filesize": filesize,
                    "addr": addr[0],
                    "response_queue": response_queue,
                    "timestamp": time.time(),
                }
                with self.gui_confirmation_lock:
                    self.pending_gui_confirmations.append(pending_item)

                try:
                    gui_decision = response_queue.get(timeout=300)  # 5 min timeout
                    if gui_decision == "accept":
                        decision = "accepted"
                except Empty:
                    print(f"Core: GUI confirmation timeout for {transfer_id}.")
                finally:
                    with self.gui_confirmation_lock:
                        self.pending_gui_confirmations = [
                            p
                            for p in self.pending_gui_confirmations
                            if p.get("id") != transfer_id
                        ]

            if decision == "accepted":
                conn.sendall(b"OK")
            else:
                conn.sendall(b"REJECTED")
                return

            os.makedirs("received_files", exist_ok=True)
            file_path = os.path.join("received_files", filename)
            received_bytes = 0

            with open(file_path, "wb") as f:
                while received_bytes < filesize:
                    if self.stop_event.is_set():
                        raise Exception("Server shutdown")
                    chunk = conn.recv(BUFFER_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    received_bytes += len(chunk)

            if received_bytes == filesize:
                conn.sendall(b"SUCCESS")
            else:
                conn.sendall(b"FAILED")
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception:  # Handle timeouts, server shutdown, etc.
            try:
                conn.sendall(b"ERROR_TRANSFER")
            except socket.error:
                pass  # Connection might already be closed
        finally:
            conn.close()

    def _listen_for_files_task(self):
        self.file_listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.file_listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.file_listener_socket.bind((self.local_ip, TCP_PORT))
            self.file_listener_socket.listen(5)
        except socket.error as e:
            print(f"Core Error (File Listener Bind): {e}")
            if self.file_listener_socket:
                self.file_listener_socket.close()
            self.file_listener_socket = None
            return

        self.file_listener_socket.settimeout(1.0)
        while not self.stop_event.is_set():
            try:
                conn, addr = self.file_listener_socket.accept()
                reception_thread = threading.Thread(
                    target=self._handle_file_reception_task,
                    args=(conn, addr),
                    daemon=False,
                )
                self.active_reception_threads.append(reception_thread)
                reception_thread.start()
                self.active_reception_threads = [
                    t for t in self.active_reception_threads if t.is_alive()
                ]
            except socket.timeout:
                continue
            except Exception:
                if self.stop_event.is_set():
                    break
                time.sleep(0.1)

        for t in self.active_reception_threads:
            if t.is_alive():
                t.join(timeout=5)
        if self.file_listener_socket:
            self.file_listener_socket.close()
            self.file_listener_socket = None

    def start_server(self):
        if self.server_running:
            return False
        self.stop_event.clear()
        self.discovery_thread = threading.Thread(
            target=self._listen_for_discovery_task, daemon=True
        )
        self.file_listener_thread = threading.Thread(
            target=self._listen_for_files_task, daemon=False
        )

        self.discovery_thread.start()
        self.file_listener_thread.start()

        time.sleep(0.2)  # Allow listener to bind
        if (
            not self.file_listener_socket and self.file_listener_thread.is_alive()
        ):  # Bind failed
            self.stop_server()
            return False
        self.server_running = True
        return True

    def stop_server(self):
        if not self.server_running:
            return
        self.stop_event.set()
        if self.discovery_thread and self.discovery_thread.is_alive():
            self.discovery_thread.join(timeout=2)
        if self.file_listener_thread and self.file_listener_thread.is_alive():
            self.file_listener_thread.join(timeout=5)
        self.server_running = False
        self._next_confirmation_id = 0
        self.pending_gui_confirmations = []

    def get_server_status(self):
        return {
            "running": self.server_running,
            "ip": self.local_ip,
            "hostname": self.hostname,
        }

    def search_devices(self, timeout=3):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.settimeout(timeout)
        found_servers = []
        try:
            udp_socket.sendto(DISCOVERY_MESSAGE.encode(), ("<broadcast>", UDP_PORT))
            while True:
                data, addr = udp_socket.recvfrom(BUFFER_SIZE)
                parts = data.decode().split(";")
                if len(parts) >= 2 and not any(
                    s["ip"] == parts[1] for s in found_servers
                ):
                    found_servers.append(
                        {
                            "hostname": parts[0],
                            "ip": parts[1],
                            "app": parts[2] if len(parts) > 2 else "",
                        }
                    )
        except socket.timeout:
            pass
        except Exception:
            pass  # Ignore search errors
        finally:
            udp_socket.close()
        return [
            s for s in found_servers if s["app"] == APP_NAME or s["app"] == ""
        ]  # Allow old clients

    def send_file(self, filepath, target_host):
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            return {"success": False, "message": "File not found or is not a file."}
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        try:
            target_ip = socket.gethostbyname(target_host)
        except socket.gaierror:
            return {
                "success": False,
                "message": f"Cannot resolve hostname '{target_host}'.",
            }

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.settimeout(10)
            try:
                tcp_socket.connect((target_ip, TCP_PORT))
                tcp_socket.sendall(f"{filename};{filesize}".encode())
                confirmation = tcp_socket.recv(BUFFER_SIZE).decode()

                if confirmation == "OK":
                    with open(filepath, "rb") as f:
                        while True:
                            chunk = f.read(BUFFER_SIZE)
                            if not chunk:
                                break
                            tcp_socket.sendall(chunk)
                    final_status = tcp_socket.recv(BUFFER_SIZE).decode()
                    if final_status == "SUCCESS":
                        return {"success": True, "message": "File sent successfully."}
                    return {
                        "success": False,
                        "message": f"Recipient error: {final_status}",
                    }
                return {
                    "success": False,
                    "message": f"Recipient rejected: {confirmation}",
                }
            except socket.timeout:
                return {"success": False, "message": "Connection timeout."}
            except socket.error as e:
                return {"success": False, "message": f"Socket error: {e}"}
            except Exception as e:
                return {"success": False, "message": f"Error: {e}"}

    def get_pending_confirmations(self):
        with self.gui_confirmation_lock:
            return [
                {
                    "id": p["id"],
                    "filename": p["filename"],
                    "filesize": p["filesize"],
                    "addr": p["addr"],
                    "timestamp": p["timestamp"],
                }
                for p in self.pending_gui_confirmations
            ]

    def respond_to_confirmation(self, transfer_id, decision):  # 'accept' or 'reject'
        with self.gui_confirmation_lock:
            for item in self.pending_gui_confirmations:
                if item["id"] == transfer_id:
                    try:
                        item["response_queue"].put_nowait(decision)
                        return True
                    except Exception:
                        return False  # Queue might be full or other issue
            return False
