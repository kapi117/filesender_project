import React, { useState, useEffect, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import "./App.css";

const API_BASE_URL =
    process.env.NODE_ENV === "development"
        ? "http://localhost:5000/api"
        : "/api";

function App() {
    const [serverStatus, setServerStatus] = useState({
        running: false,
        ip: "N/A",
        hostname: "N/A",
    });
    const [discoveredDevices, setDiscoveredDevices] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [targetHost, setTargetHost] = useState("");
    const [pendingConfirmations, setPendingConfirmations] = useState([]);
    const [logs, setLogs] = useState([]);
    const [isLoading, setIsLoading] = useState(false);

    const addLog = (message) => {
        setLogs((prevLogs) => [
            `[${new Date().toLocaleTimeString()}] ${message}`,
            ...prevLogs.slice(0, 100),
        ]);
    };

    const fetchServerStatus = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/server/status`);
            const data = await response.json();
            setServerStatus(data);
            addLog(
                `Server status updated: ${
                    data.running ? "Running" : "Stopped"
                } on ${data.ip}`
            );
        } catch (error) {
            addLog(`Error fetching server status: ${error.message}`);
        }
    }, []);

    const fetchPendingConfirmations = useCallback(async () => {
        if (!serverStatus.running) return; // Only fetch if server is supposed to be running
        try {
            const response = await fetch(`${API_BASE_URL}/file/confirmations`);
            const data = await response.json();
            setPendingConfirmations(data);
            if (data.length > 0) {
                addLog(`Fetched ${data.length} pending confirmations.`);
            }
        } catch (error) {
            addLog(`Error fetching pending confirmations: ${error.message}`);
        }
    }, [serverStatus.running]);

    useEffect(() => {
        fetchServerStatus();
        const statusInterval = setInterval(fetchServerStatus, 15000); // Periodically check server status
        const confirmationInterval = setInterval(
            fetchPendingConfirmations,
            5000
        ); // Check for confirmations more frequently
        return () => {
            clearInterval(statusInterval);
            clearInterval(confirmationInterval);
        };
    }, [fetchServerStatus, fetchPendingConfirmations]);

    const handleStartServer = async () => {
        setIsLoading(true);
        addLog("Attempting to start server...");
        try {
            const response = await fetch(`${API_BASE_URL}/server/start`, {
                method: "POST",
            });
            const data = await response.json();
            setServerStatus(data);
            addLog(
                data.message ||
                    (data.success
                        ? "Server started successfully."
                        : "Failed to start server.")
            );
        } catch (error) {
            addLog(`Error starting server: ${error.message}`);
        }
        setIsLoading(false);
    };

    const handleStopServer = async () => {
        setIsLoading(true);
        addLog("Attempting to stop server...");
        try {
            const response = await fetch(`${API_BASE_URL}/server/stop`, {
                method: "POST",
            });
            const data = await response.json();
            setServerStatus(data);
            addLog(
                data.message ||
                    (data.success
                        ? "Server stopped successfully."
                        : "Failed to stop server.")
            );
            setPendingConfirmations([]); // Clear confirmations when server stops
        } catch (error) {
            addLog(`Error stopping server: ${error.message}`);
        }
        setIsLoading(false);
    };

    const handleSearchDevices = async () => {
        setIsLoading(true);
        addLog("Searching for devices...");
        try {
            const response = await fetch(`${API_BASE_URL}/devices/search`);
            const data = await response.json();
            setDiscoveredDevices(data);
            addLog(
                data.length > 0
                    ? `Found ${data.length} devices.`
                    : "No devices found."
            );
        } catch (error) {
            addLog(`Error searching devices: ${error.message}`);
        }
        setIsLoading(false);
    };

    const onDrop = useCallback((acceptedFiles) => {
        if (acceptedFiles.length > 0) {
            setSelectedFile(acceptedFiles[0]);
            addLog(`File selected: ${acceptedFiles[0].name}`);
        }
    }, []);
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        multiple: false,
    });

    const handleSendFile = async () => {
        if (!selectedFile || !targetHost) {
            addLog("Please select a file and a target host.");
            return;
        }
        setIsLoading(true);
        addLog(`Sending ${selectedFile.name} to ${targetHost}...`);
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("hostname", targetHost);

        try {
            const response = await fetch(`${API_BASE_URL}/file/send`, {
                method: "POST",
                body: formData,
            });
            const data = await response.json();
            addLog(
                data.message ||
                    (data.success
                        ? "File sent successfully."
                        : "Failed to send file.")
            );
        } catch (error) {
            addLog(`Error sending file: ${error.message}`);
        }
        setIsLoading(false);
        setSelectedFile(null); // Clear file after attempting send
    };

    const handleFileConfirmation = async (transferId, decision) => {
        addLog(`Responding ${decision} to transfer ${transferId}...`);
        try {
            const response = await fetch(`${API_BASE_URL}/file/respond`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id: transferId, decision }),
            });
            const data = await response.json();
            addLog(
                data.message ||
                    (data.success
                        ? `Successfully responded ${decision}.`
                        : "Failed to respond.")
            );
            fetchPendingConfirmations(); // Refresh confirmations list
        } catch (error) {
            addLog(`Error responding to confirmation: ${error.message}`);
        }
    };

    return (
        <div className="App matrix-theme">
            <header className="App-header">
                <h1>FileSender Matrix</h1>
                <div className="server-status">
                    Server is:{" "}
                    <span
                        className={
                            serverStatus.running ? "status-on" : "status-off"
                        }
                    >
                        {serverStatus.running ? "ONLINE" : "OFFLINE"}
                    </span>
                    {serverStatus.running &&
                        ` (${serverStatus.hostname} - ${serverStatus.ip})`}
                </div>
            </header>

            {isLoading && (
                <div className="loading-overlay">
                    <div className="spinner"></div>
                    <p>Processing...</p>
                </div>
            )}

            <div className="main-content">
                <section className="control-panel section-box">
                    <h2>Server Control</h2>
                    {!serverStatus.running ? (
                        <button
                            onClick={handleStartServer}
                            disabled={isLoading}
                        >
                            Start Server
                        </button>
                    ) : (
                        <button onClick={handleStopServer} disabled={isLoading}>
                            Stop Server
                        </button>
                    )}
                </section>

                {pendingConfirmations.length > 0 && (
                    <section className="confirmations-panel section-box">
                        <h2>Incoming File Transfers</h2>
                        {pendingConfirmations.map((conf) => (
                            <div key={conf.id} className="confirmation-item">
                                <p>From: {conf.addr}</p>
                                <p>
                                    File: {conf.filename} (
                                    {Math.round(conf.filesize / 1024)} KB)
                                </p>
                                <p>
                                    Received:{" "}
                                    {new Date(
                                        conf.timestamp * 1000
                                    ).toLocaleTimeString()}
                                </p>
                                <button
                                    onClick={() =>
                                        handleFileConfirmation(
                                            conf.id,
                                            "accept"
                                        )
                                    }
                                    className="confirm-btn"
                                >
                                    Accept
                                </button>
                                <button
                                    onClick={() =>
                                        handleFileConfirmation(
                                            conf.id,
                                            "reject"
                                        )
                                    }
                                    className="reject-btn"
                                >
                                    Reject
                                </button>
                            </div>
                        ))}
                    </section>
                )}

                <section className="devices-panel section-box">
                    <h2>Discover Devices</h2>
                    <button
                        onClick={handleSearchDevices}
                        disabled={isLoading || !serverStatus.running}
                    >
                        Search Network
                    </button>
                    {discoveredDevices.length > 0 && (
                        <ul className="device-list">
                            {discoveredDevices.map((device) => (
                                <li
                                    key={device.ip}
                                    onClick={() =>
                                        setTargetHost(device.hostname)
                                    }
                                    className={
                                        targetHost === device.hostname
                                            ? "selected"
                                            : ""
                                    }
                                >
                                    {device.hostname} ({device.ip}){" "}
                                    {device.app && `[${device.app}]`}
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section className="send-file-panel section-box">
                    <h2>Send File</h2>
                    <div
                        {...getRootProps()}
                        className={`dropzone ${isDragActive ? "active" : ""}`}
                    >
                        <input {...getInputProps()} />
                        {selectedFile ? (
                            <p>Selected: {selectedFile.name}</p>
                        ) : isDragActive ? (
                            <p>Drop the file here ...</p>
                        ) : (
                            <p>
                                Drag 'n' drop a file here, or click to select
                                file
                            </p>
                        )}
                    </div>
                    <input
                        type="text"
                        placeholder="Target Hostname or IP"
                        value={targetHost}
                        onChange={(e) => setTargetHost(e.target.value)}
                        className="target-host-input"
                    />
                    <button
                        onClick={handleSendFile}
                        disabled={
                            isLoading ||
                            !selectedFile ||
                            !targetHost ||
                            !serverStatus.running
                        }
                    >
                        Send File
                    </button>
                </section>

                <section className="logs-panel section-box">
                    <h2>Activity Log</h2>
                    <div className="logs-container">
                        {logs.map((log, index) => (
                            <div key={index} className="log-entry">
                                {log}
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}

export default App;
