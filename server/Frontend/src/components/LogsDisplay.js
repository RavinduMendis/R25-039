import React, { useRef, useEffect } from 'react';
import './LogsDisplay.css'; 

function LogsDisplay({ logs, title = "Server Logs" }) {
  const logEndRef = useRef(null);

  // Scroll to bottom when logs update
  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  if (!logs || logs.length === 0) {
    return (
      <div className="card logs-card">
        <h2>{title}</h2>
        <p>No recent logs to display.</p>
      </div>
    );
  }

  return (
    <div className="card logs-card">
      <h2>{title}</h2>
      <div className="log-container">
        {logs.map((log, index) => (
          <div key={index} className={`log-entry log-level-${log.level_name ? log.level_name.toLowerCase() : 'info'}`}>
            <span className="log-timestamp">{log.timestamp}</span>
            <span className="log-level">[{log.level_name}]</span>
            <span className="log-message">{log.message}</span>
            {log.extra_component && <span className="log-component">({log.extra_component})</span>}
          </div>
        ))}
        <div ref={logEndRef} /> {/* For auto-scrolling */}
      </div>
    </div>
  );
}

export default LogsDisplay;