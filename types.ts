
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
  totalUsers?: number;
  activeUsers?: number;
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
  owner_id: string;
  name: string;
  token: string;
  status: BotStatus;
  created_at: number;
  license_expires_at: number;
  usersCount: number;
  description: string;
  adminChatId: string;
  welcomeMessage: string;
  logs: MessageLog[];
  connectedUsers: TelegramUser[];
  subscribers: number[]; 
  triggers: { keyword: string; response: string }[];
  buttons: { 
    text: string; 
    response: string; 
    type?: 'message' | 'request';
    adminTemplate?: string; 
  }[];
  stats: BotStats;
  settings: {
    useTopics: boolean;
    topicPerRequest: boolean;
    anonymousTopics: boolean; // Анонимные топики
    forwardToAdmin: boolean;
    antiSpam: boolean;
    showUserInfo: boolean;
    showUsername: boolean;
    autoApproveJoin: boolean;
    rateLimit: number;
    autoBanThreshold: number;
    adminMessageTemplate?: string;
  };
}

export interface User {
  id: string;
  username: string;
  email: string;
  password?: string;
  balance: number;
  botsCreated: number;
  license_expires_at: number;
  trialUsed?: boolean;
}
