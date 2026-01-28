
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus, User, MessageLog } from './types';
import Dashboard from './components/Dashboard';
import BotEditor from './components/BotEditor';
import Sidebar from './components/Sidebar';
import BroadcastManager from './components/BroadcastManager';
import Auth from './components/Auth';
import Profile from './components/Profile';
import CreateBotModal from './components/CreateBotModal';
import { api } from './services/apiService';
import { AlertCircle, X, ShieldAlert, Lock } from 'lucide-react';

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'editor' | 'broadcast' | 'profile'>('dashboard');
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState<MessageLog[]>([]);

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

  // Синхронизация данных юзера (лицензии) и ботов
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(async () => {
      try {
        const serverBots = await api.getBots(user.id);
        setBots(serverBots);
        
        // Раз в 30 секунд проверяем статус самого юзера (мог активировать ключ в другой вкладке)
        if (Date.now() % 30000 < 3000) {
           const allUsers = await fetch(`${window.location.protocol}//${window.location.hostname}:8000/api/auth/login`, {
             method: 'POST',
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({email: user.email, password: user.password})
           }).then(r => r.json());
           if (allUsers.id) {
             setUser(allUsers);
             localStorage.setItem('active_session_user', JSON.stringify(allUsers));
           }
        }
      } catch (e) {}
    }, 5000);
    return () => clearInterval(interval);
  }, [user]);

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
  const isExpired = user && user.licenseExpiresAt < Date.now();

  const handleCreateBot = async (name: string, token: string) => {
    if (!user || isExpired) return;
    const newBot: BotConfig = {
      id: Math.random().toString(36).substr(2, 9),
      ownerId: user.id,
      name,
      token,
      status: BotStatus.IDLE,
      createdAt: Date.now(),
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
      settings: { useTopics: false, autoApproveJoin: false, forwardToAdmin: true, antiSpam: true, rateLimit: 15, showUserInfo: true, showUsername: true }
    };
    await api.saveBot(user.id, newBot);
    const updatedBots = await api.getBots(user.id);
    setBots(updatedBots);
    setSelectedBotId(newBot.id);
    setActiveTab('editor');
  };

  if (loading) return null;
  if (!user) return <Auth onLogin={handleLogin} />;

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden font-sans">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} bots={bots} selectedBotId={selectedBotId} setSelectedBotId={setSelectedBotId} onAddBot={() => setIsModalOpen(true)} user={user} onLogout={handleLogout} />
      
      <main className="flex-1 overflow-y-auto p-4 md:p-12 relative no-scrollbar">
        {/* Экран блокировки при истечении лицензии */}
        {isExpired && activeTab !== 'profile' && (
          <div className="absolute inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-6">
            <div className="max-w-md w-full bg-[#111] border border-red-500/20 rounded-[2.5rem] p-10 text-center shadow-2xl">
              <div className="w-20 h-20 bg-red-500/10 text-red-500 rounded-3xl flex items-center justify-center mx-auto mb-6">
                <Lock className="w-10 h-10" />
              </div>
              <h2 className="text-2xl font-black text-white mb-4">Лицензия истекла</h2>
              <p className="text-zinc-500 text-sm mb-8">Все ваши боты остановлены. Продлите подписку в профиле, чтобы восстановить доступ к панели управления.</p>
              <button 
                onClick={() => setActiveTab('profile')}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-black py-4 rounded-2xl transition-all uppercase tracking-widest text-xs"
              >
                Перейти к оплате
              </button>
            </div>
          </div>
        )}

        <div className="max-w-6xl mx-auto">
          {activeTab === 'dashboard' && <Dashboard bots={bots} onSelectBot={(id) => { setSelectedBotId(id); setActiveTab('editor'); }} onAddBot={() => setIsModalOpen(true)} />}
          {activeTab === 'profile' && <Profile user={user} onUpdateUser={setUser} />}
          {activeTab === 'editor' && activeBot && <BotEditor bot={activeBot} onUpdate={(b) => api.saveBot(user.id, b)} onDelete={() => api.deleteBot(user.id, activeBot.id)} />}
          {activeTab === 'broadcast' && <BroadcastManager bots={bots} />}
        </div>
      </main>

      <CreateBotModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateBot} />
    </div>
  );
};

export default App;
