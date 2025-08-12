import React from 'react';
import { Link, NavLink } from 'react-router-dom'; // Using NavLink for active state
import './SideNavigation.css'; 

function SideNavigation() {
  return (
    <nav className="main-nav">
      <ul>
        <li><NavLink to="/" end>Dashboard</NavLink></li> {/* 'end' makes it active only on exact match */}
        <li><NavLink to="/metrics">Model Metrics</NavLink></li>
        <li><NavLink to="/clients">Clients</NavLink></li>
        <li><NavLink to="/logs">Logs</NavLink></li>
        <li><NavLink to="/modules">Module Status</NavLink></li>
      </ul>
    </nav>
  );
}

export default SideNavigation;