
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus, User } from './types';
import Dashboard from './components/Dashboard';
import BotEditor from './components/BotEditor';
import Sidebar from './components/Sidebar';
import BroadcastManager from './components/BroadcastManager';
import Auth from './components/Auth';
import Profile from './components/Profile';
import CreateBotModal from './components/CreateBotModal';
import { db } from './services/dbService';

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'editor' | 'broadcast' | 'profile'>('dashboard');
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // 1. При загрузке восстанавливаем сессию
  useEffect(() => {
    const savedUser = localStorage.getItem('active_session_user');
    if (savedUser) {
      const parsedUser = JSON.parse(savedUser);
      setUser(parsedUser);
      // Загружаем только ботов этого пользователя
      setBots(db.loadUserBots(parsedUser.id));
    }
  }, []);

  const handleLogin = (newUser: User) => {
    setUser(newUser);
    localStorage.setItem('active_session_user', JSON.stringify(newUser));
    setBots(db.loadUserBots(newUser.id));
    setActiveTab('dashboard');
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('active_session_user');
    setBots([]);
    setSelectedBotId(null);
  };

  const activeBot = bots.find(b => b.id === selectedBotId) || null;

  const handleCreateBot = (name: string, token: string) => {
    if (!user) return;
    
    const newBot: BotConfig = {
      id: Math.random().toString(36).substr(2, 9),
      ownerId: user.id,
      name,
      token,
      status: BotStatus.IDLE,
      createdAt: Date.now(),
      usersCount: 0,
      description: 'Автономный инстанс',
      adminChatId: '',
      welcomeMessage: `Привет! Я — ${name}. Отправьте сообщение или воспользуйтесь меню.`,
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

    const allBots = db.loadAllBots();
    const updatedAll = [...allBots, newBot];
    db.saveBots(updatedAll);
    
    setBots(db.loadUserBots(user.id));
    setSelectedBotId(newBot.id);
    setActiveTab('editor');
  };

  const updateBot = (updatedBot: BotConfig) => {
    const allBots = db.loadAllBots();
    const updatedAll = allBots.map(b => b.id === updatedBot.id ? updatedBot : b);
    db.saveBots(updatedAll);
    setBots(db.loadUserBots(user!.id));
  };

  const deleteBot = (id: string) => {
    const allBots = db.loadAllBots();
    const updatedAll = allBots.filter(b => b.id !== id);
    db.saveBots(updatedAll);
    setBots(db.loadUserBots(user!.id));
    if (selectedBotId === id) setSelectedBotId(null);
  };

  if (!user) return <Auth onLogin={handleLogin} />;

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden">
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
      
      <main className="flex-1 overflow-y-auto p-4 md:p-8 relative">
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
            <div className="flex flex-col items-center justify-center h-[70vh] text-zinc-600">
               <p className="text-lg font-medium text-zinc-400">Выберите бота в боковой панели</p>
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
