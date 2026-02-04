
import React, { useState, useEffect } from 'react';
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

  const syncData = async (userId: string) => {
    try {
        const serverBots = await api.getBots(userId);
        setBots(serverBots || []);
        // Также можно запросить обновленные данные профиля здесь, если нужно
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    const init = async () => {
      try {
        const savedUserStr = localStorage.getItem('active_session_user');
        if (savedUserStr && savedUserStr !== "undefined" && savedUserStr !== "null") {
          const parsedUser = JSON.parse(savedUserStr);
          if (parsedUser && parsedUser.id) {
            setUser(parsedUser);
            await syncData(parsedUser.id);
          }
        }
      } catch (e) {
        localStorage.removeItem('active_session_user');
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const handleLogin = async (newUser: User) => {
    setUser(newUser);
    localStorage.setItem('active_session_user', JSON.stringify(newUser));
    await syncData(newUser.id);
    setActiveTab('dashboard');
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('active_session_user');
    setBots([]);
    setSelectedBotId(null);
    setActiveTab('dashboard');
  };

  const handleCreateBot = async (name: string, token: string) => {
    if (!user) return;
    const newBotId = `bot_${Math.random().toString(36).substr(2, 9)}`;
    const newBot: BotConfig = {
      id: newBotId,
      owner_id: user.id,
      name,
      token,
      status: BotStatus.IDLE,
      created_at: Date.now(),
      license_expires_at: Date.now() + (3 * 24 * 3600 * 1000), // Триальный период 3 дня
      usersCount: 0,
      description: 'Новый бот BotEngine',
      adminChatId: '',
      welcomeMessage: `Добро пожаловать в ${name}!`,
      logs: [],
      connectedUsers: [],
      subscribers: [],
      triggers: [],
      buttons: [],
      stats: { totalMessages: 0, incomingToday: 0, outgoingToday: 0, activeUsers24h: 0, bannedCount: 0, history: [] },
      settings: { 
        useTopics: false, 
        topicPerRequest: false, 
        anonymousTopics: false,
        autoApproveJoin: false, 
        forwardToAdmin: true, 
        antiSpam: true, 
        rateLimit: 15, 
        showUserInfo: true, 
        showUsername: true, 
        autoBanThreshold: 0,
        showHeaderId: true,
        showHeaderName: true,
        showHeaderUsername: true
      }
    };
    try {
      await api.saveBot(user.id, newBot);
      setBots(prev => [...prev, newBot]);
      setSelectedBotId(newBotId);
      setActiveTab('editor');
    } catch (e) {
      alert("Ошибка при создании бота");
    }
  };

  if (loading) return null;
  if (!user) return <Auth onLogin={handleLogin} />;
  const activeBot = bots.find(b => b.id === selectedBotId) || null;

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden font-sans relative">
      {isSidebarOpen && <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden" onClick={() => setIsSidebarOpen(false)} />}
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
          <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 bg-zinc-800 rounded-lg text-white">
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>
        <main className="flex-1 overflow-y-auto p-4 md:p-12 no-scrollbar">
          <div className="max-w-6xl mx-auto">
            {activeTab === 'dashboard' && <Dashboard bots={bots} onSelectBot={(id) => { setSelectedBotId(id); setActiveTab('editor'); }} onAddBot={() => setIsModalOpen(true)} />}
            {activeTab === 'profile' && <Profile user={user} bots={bots} onUpdateBots={setBots} />}
            {activeTab === 'editor' && activeBot && (
                <BotEditor 
                    bot={activeBot} 
                    onUpdate={(u) => setBots(prev => prev.map(b => b.id === u.id ? u : b))} 
                    onDelete={() => setBots(prev => prev.filter(b => b.id !== activeBot.id))} 
                />
            )}
            {activeTab === 'broadcast' && <BroadcastManager bots={bots} />}
          </div>
        </main>
      </div>
      <CreateBotModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleCreateBot} />
    </div>
  );
};

export default App;
