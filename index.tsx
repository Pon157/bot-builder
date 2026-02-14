import React from 'react';
import { createRoot } from 'react-dom/client';

// Импортируем CSS шрифтов напрямую (Vite сам найдет их в node_modules)
import "@fontsource/inter/index.css";
import "@fontsource/jetbrains-mono/index.css";

// Импортируем основной CSS (в котором Tailwind)
import './index.css'; 

import App from './App';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

const root = createRoot(rootElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
