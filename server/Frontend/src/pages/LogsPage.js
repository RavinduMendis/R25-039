import React from 'react';
import LogsDisplay from '../components/LogsDisplay';

function LogsPage({ logs }) {
    if (!logs || logs.length === 0) {
        return <div className="card page-container"><h2>Server Logs</h2><p>No logs to display.</p></div>;
    }
    return (
        <div className="page-container">
            <h1>Server Logs</h1>
            <LogsDisplay logs={logs} />
        </div>
    );
}

export default LogsPage;