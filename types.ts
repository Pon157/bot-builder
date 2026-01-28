
export enum BotStatus {
  IDLE = 'IDLE',
  RUNNING = 'RUNNING',
  ERROR = 'ERROR',
  STARTING = 'STARTING'
}

export interface TelegramUser {
  id: number;
  first_name: string;
  username?: string;
  is_banned: boolean;
  is_active: boolean; 
  joined_at: number;
  last_seen?: number;
  thread_id?: number;
  warns: number;
}

export interface StatPoint {
  date: string;
  incoming: number;
  outgoing: number;
}

export interface BotStats {
  totalMessages: number;
  incomingToday: number;
  outgoingToday: number;
  bannedCount: number;
  history: StatPoint[];
  activeUsers24h: number;
}

export interface MessageLog {
  id: string;
  timestamp: number;
  type: 'info' | 'error' | 'incoming' | 'outgoing' | 'system';
  text: string;
  code?: string;
}

export interface BotConfig {
  id: string;
  ownerId: string;
  name: string;
  token: string;
  status: BotStatus;
  createdAt: number;
  usersCount: number;
  description: string;
  adminChatId: string;
  welcomeMessage: string;
  logs: MessageLog[];
  connectedUsers: TelegramUser[];
  subscribers: number[]; // Список ID всех пользователей для рассылки
  triggers: { keyword: string; response: string }[];
  buttons: { text: string; response: string }[];
  stats: BotStats;
  settings: {
    useTopics: boolean;
    forwardToAdmin: boolean;
    antiSpam: boolean;
    showUserInfo: boolean;
    showUsername: boolean;
    autoApproveJoin: boolean;
    rateLimit: number;
  };
}

export interface User {
  id: string;
  username: string;
  email: string;
  password?: string;
  licenseExpiresAt: number;
  trialUsed: boolean;
  activeKey?: string;
  balance: number;
  botsCreated: number;
}
