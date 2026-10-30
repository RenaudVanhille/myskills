import { createTheme } from "@mui/material/styles";

// Thème du client
export const theme = createTheme({
  palette: {
    primary: { main: '#0b3d91', contrastText: '#ffffff' },
    secondary: { main: '#f97316' },
    error: { main: '#b91c1c' },
    background: { default: '#ffffff', paper: '#f1f5f9' },
    text: { primary: '#0f172a', secondary: '#64748b' },
    divider: '#e2e8f0',
  },
  typography: { fontFamily: 'Marianne, Arial, sans-serif' },
  shape: { borderRadius: 8 },
});
