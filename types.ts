
export enum BotStatus {
  IDLE = 'IDLE',
  RUNNING = 'RUNNING',
  ERROR = 'ERROR',
  STARTING = 'STARTING'
}

// Added SubscriptionPlan type
export type SubscriptionPlan = 'FREE' | 'PRO' | 'ENTERPRISE';

export interface TelegramUser {
  id: number;
  first_name: string;
  username?: string;
  is_banned: boolean;
  is_active: boolean; // false если юзер сам заблокировал бота
  joined_at: number;
}

export interface StatPoint {
  date: string;
  incoming: number;
  outgoing: number;
}

// Added activeUsers24h to BotStats
export interface BotStats {
  totalMessages: number;
  incomingToday: number;
  outgoingToday: number;
  bannedCount: number;
  history: StatPoint[];
  activeUsers24h: number;
}

// Added MessageLog interface for bot console
export interface MessageLog {
  id: string;
  timestamp: number;
  type: 'info' | 'error' | 'incoming' | 'outgoing' | 'system';
  text: string;
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
  triggers: any[];
  buttons: any[];
  stats: BotStats;
  settings: {
    useTopics: boolean;
    forwardToAdmin: boolean;
    antiSpam: boolean;
    showUserInfo: boolean;
    autoApproveJoin: boolean; // Added missing property
    rateLimit: number; // Added missing property
  };
}

export interface User {
  id: string;
  username: string;
  email: string;
  password?: string; // Added optional password for registration
  subscription: SubscriptionPlan; // Updated to use the type
  balance: number;
  botsCreated: number;
}
