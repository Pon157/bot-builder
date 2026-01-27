
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
import { AlertCircle, X } from 'lucide-react';

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

  // Poll for logs/errors
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(async () => {
      const serverBots = await api.getBots(user.id);
      
      // Check for new errors
      serverBots.forEach(bot => {
        const lastLog = bot.logs?.[0];
        if (lastLog?.type === 'error' && lastLog.code === 'TOPIC_ERROR') {
          if (!toasts.find(t => t.id === lastLog.id)) {
            setToasts(prev => [...prev, lastLog]);
            // Auto remove after 10s
            setTimeout(() => {
              setToasts(prev => prev.filter(t => t.id !== lastLog.id));
            }, 10000);
          }
        }
      });
      
      setBots(serverBots);
    }, 3000);
    return () => clearInterval(interval);
  }, [user, toasts]);

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
      usersCount: 0,
      description: 'Cloud Instance',
      adminChatId: '',
      welcomeMessage: `Добро пожаловать в ${name}!`,
      logs: [],
      connectedUsers: [],
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

  const updateBot = async (updatedBot: BotConfig) => {
    if (!user) return;
    await api.saveBot(user.id, updatedBot);
    const updatedBots = await api.getBots(user.id);
    setBots(updatedBots);
  };

  const deleteBot = async (id: string) => {
    if (!user) return;
    await api.deleteBot(user.id, id);
    const updatedBots = await api.getBots(user.id);
    setBots(updatedBots);
    if (selectedBotId === id) setSelectedBotId(null);
  };

  if (loading) return null;
  if (!user) return <Auth onLogin={handleLogin} />;

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden font-sans">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} bots={bots} selectedBotId={selectedBotId} setSelectedBotId={setSelectedBotId} onAddBot={() => setIsModalOpen(true)} user={user} onLogout={handleLogout} />
      
      <main className="flex-1 overflow-y-auto p-4 md:p-12 relative no-scrollbar">
        {/* Toast Overlay */}
        <div className="fixed top-8 right-8 z-[100] flex flex-col gap-3 max-w-sm w-full">
          {toasts.map(toast => (
            <div key={toast.id} className="bg-red-500/10 border border-red-500/20 backdrop-blur-xl p-4 rounded-2xl shadow-2xl animate-in slide-in-from-right-full duration-300 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-xs font-black text-white uppercase tracking-widest mb-1">Критическая ошибка</p>
                <p className="text-[10px] text-zinc-400 leading-relaxed">{toast.text}</p>
              </div>
              <button onClick={() => setToasts(prev => prev.filter(t => t.id !== toast.id))} className="text-zinc-600 hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="max-w-6xl mx-auto">
          {activeTab === 'dashboard' && <Dashboard bots={bots} onSelectBot={(id) => { setSelectedBotId(id); setActiveTab('editor'); }} onAddBot={() => setIsModalOpen(true)} />}
          {activeTab === 'profile' && <Profile user={user} onUpdateUser={setUser} />}
          {activeTab === 'editor' && activeBot && <BotEditor bot={activeBot} onUpdate={updateBot} onDelete={() => deleteBot(activeBot.id)} />}
          {activeTab === 'editor' && !activeBot && <div className="flex flex-col items-center justify-center h-[60vh] text-zinc-600"><p className="text-lg font-bold text-zinc-500 uppercase tracking-widest">Выберите инстанс из списка</p></div>}
          {activeTab === 'broadcast' && <BroadcastManager bots={bots} />}
        </div>
      </main>

      <CreateBotModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateBot} />
    </div>
  );
};

export default App;
