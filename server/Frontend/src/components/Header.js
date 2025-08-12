import React, { useState, useEffect } from 'react';
import './Header.css'; 
// Place your logo.png in the `public` folder, e.g., public/images/logo.png
// Then you can reference it directly as src="/images/logo.png"
// Alternatively, if you have logo.svg in src/, use:
import logo from './logo.png'; 

function Header() {
  const [dateTime, setDateTime] = useState(new Date().toLocaleString());

  useEffect(() => {
    const timer = setInterval(() => {
      setDateTime(new Date().toLocaleString());
    }, 1000);
    return () => clearInterval(timer); // Cleanup
  }, []);

  return (
    <header className="dashboard-header">
      <div className="header-top">
        <div className="logo">
          {/* Use /images/logo.png if you put it in public/images/ */}
          <img src={logo} alt="FL Logo" /> 
          <span className="logo-text">FEDERATED LEARNING FRAMEWORK</span>
        </div>
        <div className="datetime-display" id="datetime">{dateTime}</div>
      </div>
    </header>
  );
}

export default Header;