
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

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'editor' | 'broadcast' | 'profile'>('dashboard');
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  // Загрузка сессии и данных с сервера
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
      settings: {
        useTopics: false,
        autoApproveJoin: false,
        forwardToAdmin: true,
        antiSpam: true,
        rateLimit: 15
      }
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
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        bots={bots}
        selectedBotId={selectedBotId}
        setSelectedBotId={setSelectedBotId}
        onAddBot={() => setIsModalOpen(true)}
        user={user}
        onLogout={handleLogout}
      />
      
      <main className="flex-1 overflow-y-auto p-4 md:p-12 relative no-scrollbar">
        <div className="max-w-6xl mx-auto">
          {activeTab === 'dashboard' && (
            <Dashboard 
              bots={bots} 
              onSelectBot={(id) => { setSelectedBotId(id); setActiveTab('editor'); }} 
              onAddBot={() => setIsModalOpen(true)} 
            />
          )}
          
          {activeTab === 'profile' && <Profile user={user} onUpdateUser={setUser} />}

          {activeTab === 'editor' && activeBot && (
            <BotEditor 
              bot={activeBot} 
              onUpdate={updateBot} 
              onDelete={() => deleteBot(activeBot.id)}
            />
          )}
          
          {activeTab === 'editor' && !activeBot && (
            <div className="flex flex-col items-center justify-center h-[60vh] text-zinc-600">
               <p className="text-lg font-bold text-zinc-500 uppercase tracking-widest">Выберите инстанс из списка</p>
            </div>
          )}

          {activeTab === 'broadcast' && <BroadcastManager bots={bots} />}
        </div>
      </main>

      <CreateBotModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSubmit={handleCreateBot} 
      />
    </div>
  );
};

export default App;
