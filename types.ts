
export enum BotStatus {
  IDLE = 'IDLE',
  RUNNING = 'RUNNING',
  ERROR = 'ERROR',
  STARTING = 'STARTING'
}

export type SubscriptionPlan = 'FREE' | 'PRO' | 'ENTERPRISE';

export interface User {
  id: string;
  username: string;
  email: string;
  password?: string;
  subscription: SubscriptionPlan;
  subExpiresAt?: number;
  balance: number;
  botsCreated: number;
}

export interface TelegramUser {
  id: number;
  first_name: string;
  username?: string;
  last_seen: number;
}

export interface MessageLog {
  id: string;
  timestamp: number;
  type: 'info' | 'error' | 'incoming' | 'outgoing' | 'system';
  text: string;
}

export interface BotTrigger {
  keyword: string;
  response: string;
}

export interface BotButton {
  text: string;
  response: string;
}

export interface BotConfig {
  id: string;
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
  triggers: BotTrigger[];
  buttons: BotButton[];
  settings: {
    useTopics: boolean;
    autoApproveJoin: boolean;
    forwardToAdmin: boolean;
    antiSpam: boolean;
    rateLimit: number;
  };
}
