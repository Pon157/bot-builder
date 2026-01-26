
import { BotConfig } from '../types';

const STORAGE_KEY = 'botengine_pro_db';

export const db = {
  saveBots: (bots: BotConfig[]) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bots));
  },
  
  loadBots: (): BotConfig[] => {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  },
  
  addLog: (botId: string, log: Omit<import('../types').MessageLog, 'id'>) => {
    const bots = db.loadBots();
    const bot = bots.find(b => b.id === botId);
    if (bot) {
      const newLog = { ...log, id: Math.random().toString(36).substr(2, 9) };
      bot.logs = [newLog, ...bot.logs].slice(0, 50); // Keep last 50
      db.saveBots(bots);
      return newLog;
    }
    return null;
  }
};
