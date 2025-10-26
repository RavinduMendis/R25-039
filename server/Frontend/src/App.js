import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import { Box, CssBaseline, Drawer, AppBar, Toolbar, Typography, List, ListItem, ListItemButton, ListItemIcon, ListItemText, IconButton, Button, Menu, MenuItem } from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import BarChartIcon from '@mui/icons-material/BarChart';
import PeopleIcon from '@mui/icons-material/People';
import DnsIcon from '@mui/icons-material/Dns';
import DescriptionIcon from '@mui/icons-material/Description';
import InfoIcon from '@mui/icons-material/Info';
import LanguageIcon from '@mui/icons-material/Language'; 

// --- Import Real Page Components ---
import DashboardPage from './pages/DashboardPage';
import PerformancePage from './pages/PerformancePage';
import ClientsPage from './pages/ClientsPage';
import SystemHealthPage from './pages/SystemHealthPage';
import LogsPage from './pages/LogsPage';

const drawerWidth = 240;
const appTitle = ""; // Federated Learning Analytics & Monitoring Environment

const navItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Performance', icon: <BarChartIcon />, path: '/performance' },
  { text: 'Clients', icon: <PeopleIcon />, path: '/clients' },
  { text: 'System Health', icon: <DnsIcon />, path: '/system-health' },
  { text: 'Logs', icon: <DescriptionIcon />, path: '/logs' },
];

/**
 * Component to display the current time and date, plus header buttons.
 */
const SystemInfo = () => {
  const [currentDateTime, setCurrentDateTime] = useState(new Date());
  const [anchorEl, setAnchorEl] = useState(null);
  const open = Boolean(anchorEl);

  // Use current time and date based on the user's location (Sri Lanka)
  const timeOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
  const dateOptions = { year: 'numeric', month: 'short', day: 'numeric' };

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentDateTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  // Set the locale to 'en-US' or another preferred format
  const formattedTime = currentDateTime.toLocaleTimeString('en-US', timeOptions);
  const formattedDate = currentDateTime.toLocaleDateString('en-US', dateOptions);

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      {/* Time and Date Display */}
      <Typography variant="body2" color="inherit">
        {formattedDate} | {formattedTime}
      </Typography>

      {/* Visit Website Button */}
      <Button
        component="a" 
        href="https://k0k1s.github.io/r25-039" // Update this URL!
        target="_blank" 
        rel="noopener noreferrer"
        color="inherit"
        startIcon={<LanguageIcon />}
        sx={{ textTransform: 'none' }}
      >
        Website
      </Button>

      {/* About Section */}
      <Button
        id="about-button"
        aria-controls={open ? 'about-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
        onClick={handleMenuOpen}
        color="inherit"
        startIcon={<InfoIcon />}
        sx={{ textTransform: 'none' }}
      >
        About
      </Button>
      <Menu
        id="about-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={handleMenuClose}
        MenuListProps={{
          'aria-labelledby': 'about-button',
        }}
      >
        <MenuItem onClick={handleMenuClose}>Version: 1.0.0</MenuItem>
      </Menu>
    </Box>
  );
};


function App() {
  return (
    <Router>
      <Box sx={{ display: 'flex' }}>
        <CssBaseline />
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, background: '#0d1b2a' }}>
          <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
            
            {/* Left Section: Logo and Title */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {/* LOGO: Correctly referencing the /public/logo.png file */}
              <img 
                src={`${process.env.PUBLIC_URL}/logo.png`} 
                alt="F.L.A.M.E Logo" 
                style={{ height: 60 }} 
              />
              <Typography variant="h5" noWrap component="div" sx={{ fontWeight: 600 }}>
                {appTitle}
              </Typography>
            </Box>

            {/* Right Section: System Info (Time, Date, Website, About) */}
            <SystemInfo />

          </Toolbar>
        </AppBar>
        <Drawer
          variant="permanent"
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box' },
          }}
        >
          <Toolbar />
          <Box sx={{ overflow: 'auto' }}>
            <List>
              {navItems.map((item) => (
                <ListItem key={item.text} disablePadding>
                  <ListItemButton component={NavLink} to={item.path} 
                    sx={{
                        '&.active': {
                            backgroundColor: 'rgba(25, 118, 210, 0.08)',
                            borderRight: '3px solid #1976d2',
                            color: '#1976d2',
                            '& .MuiListItemIcon-root': {
                                color: '#1976d2'
                            }
                        }
                    }}>
                    <ListItemIcon>{item.icon}</ListItemIcon>
                    <ListItemText primary={item.text} />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          </Box>
        </Drawer>
        <Box component="main" sx={{ flexGrow: 1, p: 3, background: '#f4f6f8', minHeight: '100vh' }}>
          <Toolbar />
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/performance" element={<PerformancePage />} />
            <Route path="/clients" element={<ClientsPage />} />
            <Route path="/system-health" element={<SystemHealthPage />} />
            <Route path="/logs" element={<LogsPage />} />
          </Routes>
        </Box>
      </Box>
    </Router>
  );
}

export default App;