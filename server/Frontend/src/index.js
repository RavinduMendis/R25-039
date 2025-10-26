import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';

// You can customize your application's theme here
const theme = createTheme({
  palette: {
    primary: {
      main: '#1a237e', // A deep indigo color
    },
    background: {
      default: '#f4f6f8', // A light grey background
    },
  },
  typography: {
    fontFamily: 'Roboto, sans-serif',
  },
});

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      {/* CssBaseline helps normalize styles across browsers */}
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);