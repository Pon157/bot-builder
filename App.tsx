
import React, { useState, useEffect, useCallback } from 'react';
import { BotConfig, BotStatus, User } from './types';
import Dashboard from './components/Dashboard';
import BotEditor from './components/BotEditor';
import Sidebar from './components/Sidebar';
import BroadcastManager from './components/BroadcastManager';
import Auth from './components/Auth';
import Profile from './components/Profile';
import CreateBotModal from './components/CreateBotModal';
import { api } from './services/apiService';
import { Menu, X } from 'lucide-react';

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'editor' | 'broadcast' | 'profile'>('dashboard');
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      const savedUser = localStorage.getItem('active_session_user');
      if (savedUser) {
        const parsedUser = JSON.parse(savedUser);
        setUser(parsedUser);
        const serverBots = await api.getBots(parsedUser.id);
        setBots(serverBots);
      }
      setLoading(false);
    };
    init();
  }, []);

  useEffect(() => {
    if (!user) return;
    const interval = setInterval(async () => {
      try {
        const serverBots = await api.getBots(user.id);
        setBots(prev => {
          return prev.map(localBot => {
            const serverBot = serverBots.find(b => b.id === localBot.id);
            if (!serverBot) return localBot;
            return {
              ...localBot,
              status: serverBot.status,
              stats: serverBot.stats,
              usersCount: serverBot.usersCount,
              connectedUsers: serverBot.connectedUsers,
              licenseExpiresAt: serverBot.licenseExpiresAt,
              logs: serverBot.logs || [] // КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Переносим логи
            };
          });
        });
      } catch (e) {}
    }, 10000); // Сокращаем до 10 сек для лучшего UX в консоли
    return () => clearInterval(interval);
  }, [user]);

  const handleUpdateBotLocally = useCallback((updatedBot: BotConfig) => {
    setBots(prev => prev.map(b => b.id === updatedBot.id ? updatedBot : b));
  }, []);

  const handleLogin = async (newUser: User) => {
    setUser(newUser);
    localStorage.setItem('active_session_user', JSON.stringify(newUser));
    const serverBots = await api.getBots(newUser.id);
    setBots(serverBots);
    setActiveTab('dashboard');
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('active_session_user');
    setBots([]);
    setSelectedBotId(null);
  };

  const activeBot = bots.find(b => b.id === selectedBotId) || null;

  const handleCreateBot = async (name: string, token: string) => {
    if (!user) return;
    const newBot: BotConfig = {
      id: Math.random().toString(36).substr(2, 9),
      ownerId: user.id,
      name,
      token,
      status: BotStatus.IDLE,
      createdAt: Date.now(),
      licenseExpiresAt: Date.now() + (3 * 24 * 3600 * 1000),
      usersCount: 0,
      description: 'Cloud Instance',
      adminChatId: '',
      welcomeMessage: `Добро пожаловать в ${name}!`,
      logs: [],
      connectedUsers: [],
      subscribers: [],
      triggers: [],
      buttons: [],
      stats: { totalMessages: 0, incomingToday: 0, outgoingToday: 0, activeUsers24h: 0, bannedCount: 0, history: [] },
      settings: { useTopics: false, topicPerRequest: false, autoApproveJoin: false, forwardToAdmin: true, antiSpam: true, rateLimit: 15, showUserInfo: true, showUsername: true, autoBanThreshold: 0 }
    };
    await api.saveBot(user.id, newBot);
    setBots(prev => [...prev, newBot]);
    setSelectedBotId(newBot.id);
    setActiveTab('editor');
  };

  if (loading) return null;
  if (!user) return <Auth onLogin={handleLogin} />;

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden font-sans relative">
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={(tab) => { setActiveTab(tab); setIsSidebarOpen(false); }} 
        bots={bots} 
        selectedBotId={selectedBotId} 
        setSelectedBotId={(id) => { setSelectedBotId(id); setActiveTab('editor'); setIsSidebarOpen(false); }} 
        onAddBot={() => { setIsModalOpen(true); setIsSidebarOpen(false); }} 
        user={user} 
        onLogout={handleLogout}
        isOpen={isSidebarOpen}
      />
      
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <header className="md:hidden flex items-center justify-between p-4 bg-[#121212] border-b border-zinc-800 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-blue-600 rounded flex items-center justify-center font-bold text-white text-[10px]">BE</div>
            <span className="font-black text-sm uppercase tracking-wider text-white">BotEngine <span className="text-blue-500">Pro</span></span>
          </div>
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="p-2 bg-zinc-800 rounded-lg text-white"
          >
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>

        <main className="flex-1 overflow-y-auto p-4 md:p-12 no-scrollbar">
          <div className="max-w-6xl mx-auto">
            {activeTab === 'dashboard' && <Dashboard bots={bots} onSelectBot={(id) => { setSelectedBotId(id); setActiveTab('editor'); }} onAddBot={() => setIsModalOpen(true)} />}
            {activeTab === 'profile' && <Profile user={user} bots={bots} onUpdateBots={setBots} />}
            {activeTab === 'editor' && activeBot && <BotEditor bot={activeBot} onUpdate={handleUpdateBotLocally} onDelete={() => api.deleteBot(user.id, activeBot.id)} />}
            {activeTab === 'broadcast' && <BroadcastManager bots={bots} />}
          </div>
        </main>
      </div>

      <CreateBotModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateBot} />
    </div>
  );
};

export default App;
