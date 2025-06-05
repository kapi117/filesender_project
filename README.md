# FileSender

A command-line application for transferring files between computers on the same local network.

## Features

* **Discoverable Servers**: Servers running `filesender` can be discovered by other instances on the network.
* **Direct File Transfer**: Send files directly to a chosen recipient.
* **Recipient Confirmation**: The recipient is prompted to accept or reject incoming files.
* **Cross-Platform**: Written in Python, should work on any OS with Python installed.

## Prerequisites

* Python 3.6+
* Computers must be on the same local network.

## Setup

No special installation is required beyond having Python. The application consists of `filesender.py` and `config.py`.

## Usage

The application is controlled via the command line.

### 1. Start the Server

On the computer that will receive files, open a terminal in the project directory and run:

```bash
python filesender.py start
```

The server will start and announce its presence. It will display its IP address and hostname, making it visible to others. It will listen for discovery requests and incoming file transfers until you stop it (e.g., with Ctrl+C).

### 2. Search for Servers

On another computer (or the same one) that wants to send a file or see available servers, open a terminal and run:

```bash
python filesender.py search
```

This command will broadcast a discovery message on the network and list any `filesender` servers that respond. The output will show the hostname and IP address of each found server.

### 3. Send a File

To send a file, use the `send` command followed by the path to the file and the hostname or IP address of the recipient (as found by the `search` command).

```bash
python filesender.py send [filepath] [hostname_or_ip]
```

Example:

```bash
python filesender.py send ./my_document.txt my-laptop
```

Or using an IP address:

```bash
python filesender.py send /path/to/archive.zip 192.168.1.102
```

The sender will attempt to connect to the recipient. The recipient (running the `start` command) will be prompted to accept or reject the incoming file.

* If the recipient accepts, the file transfer will begin.
* If the recipient rejects, the sender will be notified.

Received files are saved in a `received_files` directory in the location where the `filesender.py start` command was executed.

## Configuration

Network settings are in `config.py`:

* `TCP_PORT = 60000`: Port for TCP file transfer.
* `UDP_PORT = 60001`: Port for UDP discovery.
* `DISCOVERY_MESSAGE = "FILESENDER_DISCOVERY"`: Message used for server discovery.
* `BUFFER_SIZE = 4096`: Data chunk size for transfers.

## Firewall Configuration

For `filesender` to work correctly, your system's firewall must allow traffic on the configured UDP and TCP ports:

* **UDP Port `60001` (or as configured in `config.py`)**: Must be open for incoming and outgoing traffic for device discovery. UDP broadcasts must be allowed on your network segment.
* **TCP Port `60000` (or as configured in `config.py`)**: Must be open for incoming traffic on the server machine to receive files, and outgoing on the client machine to send files.

Consult your operating system's or firewall software's documentation for instructions on how to open these ports.

## Troubleshooting

* **No servers found**:
  * Ensure the server instance is running (`python filesender.py start`) on the target machine.
  * Check that both devices are on the same network.
  * Verify firewall settings on both machines allow UDP traffic on the discovery port.
  * Some network configurations might block UDP broadcasts.
* **Connection refused when sending**:
  * Ensure the server instance is running on the target machine.
  * Verify the hostname or IP address is correct.
  * Check firewall settings on the server machine to allow TCP traffic on the file transfer port.
* **File transfer fails**:
  * Check for network interruptions.
  * Ensure sufficient disk space on the receiving machine.
