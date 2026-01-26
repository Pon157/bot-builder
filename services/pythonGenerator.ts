import { BotConfig } from '../types';

// This service is now internal only and not exposed to the UI
// Fix: Added bot parameter to match the function call signature in CodeViewer.tsx
export const generatePythonCode = (bot: BotConfig) => "";
