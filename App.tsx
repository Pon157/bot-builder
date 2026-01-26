
import React, { useState, useEffect } from 'react';
import { BotConfig, BotStatus, User, SubscriptionPlan } from './types';
import Dashboard from './components/Dashboard';
import BotEditor from './components/BotEditor';
import Sidebar from './components/Sidebar';
import BroadcastManager from './components/BroadcastManager';
import CodeViewer from './components/CodeViewer';
import Auth from './components/Auth';
import Profile from './components/Profile';
import CreateBotModal from './components/CreateBotModal';
import { db } from './services/dbService';

const App: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [bots, setBots] = useState<BotConfig[]>([]);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'editor' | 'broadcast' | 'code' | 'profile'>('dashboard');
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    const savedUser = localStorage.getItem('botengine_user');
    if (savedUser) {
        setUser(JSON.parse(savedUser));
    } else {
        // Initial mock user if first time
    }
    setBots(db.loadBots());
  }, []);

  useEffect(() => {
    if (user) {
        localStorage.setItem('botengine_user', JSON.stringify(user));
    }
  }, [user]);

  const handleLogin = (newUser: User) => {
    const enrichedUser: User = {
        ...newUser,
        subscription: 'FREE',
        balance: 0,
        botsCreated: bots.length
    };
    setUser(enrichedUser);
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('botengine_user');
  };

  const activeBot = bots.find(b => b.id === selectedBotId) || null;

  const handleCreateBot = (name: string, token: string) => {
    if (!user) return;
    
    // Subscription Check
    if (user.subscription === 'FREE' && bots.length >= 1) {
        alert("Free tier is limited to 1 bot. Please upgrade to PRO for more.");
        setActiveTab('profile');
        return;
    }

    const newBot: BotConfig = {
      id: Math.random().toString(36).substr(2, 9),
      name,
      token,
      status: BotStatus.IDLE,
      createdAt: Date.now(),
      usersCount: 0,
      description: 'Standard support instance',
      adminChatId: '',
      welcomeMessage: `Hello! I am ${name}. How can I help you today?`,
      isSupportBot: true,
      logs: [],
      connectedUsers: [],
      actions: [],
      triggers: [],
      buttons: [],
      antiSpam: { enabled: false, rateLimit: 10 }
    };

    const updatedBots = [...bots, newBot];
    setBots(updatedBots);
    db.saveBots(updatedBots);
    setSelectedBotId(newBot.id);
    setActiveTab('editor');
    
    setUser({ ...user, botsCreated: updatedBots.length });
  };

  const updateBot = (updatedBot: BotConfig) => {
    const newBots = bots.map(b => b.id === updatedBot.id ? updatedBot : b);
    setBots(newBots);
    db.saveBots(newBots);
  };

  const deleteBot = (id: string) => {
    const newBots = bots.filter(b => b.id !== id);
    setBots(newBots);
    db.saveBots(newBots);
    if (selectedBotId === id) setSelectedBotId(null);
    if (user) setUser({ ...user, botsCreated: newBots.length });
  };

  if (!user) return <Auth onLogin={handleLogin} />;

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-zinc-300 overflow-hidden selection:bg-blue-500/30">
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
          
          {activeTab === 'profile' && (
              <Profile 
                user={user} 
                onUpdateUser={(u) => setUser(u)} 
              />
          )}

          {activeTab === 'editor' && activeBot && (
            <BotEditor 
              bot={activeBot} 
              onUpdate={updateBot} 
              onDelete={() => deleteBot(activeBot.id)}
              onGenerateCode={() => setActiveTab('code')}
            />
          )}
          
          {activeTab === 'editor' && !activeBot && (
            <div className="flex flex-col items-center justify-center h-[70vh] text-zinc-600">
              <div className="w-20 h-20 mb-6 bg-zinc-900 rounded-3xl flex items-center justify-center border border-zinc-800">
                <svg className="w-10 h-10 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <p className="text-lg font-medium text-zinc-400">Select an instance from the sidebar</p>
            </div>
          )}

          {activeTab === 'broadcast' && <BroadcastManager bots={bots} />}

          {activeTab === 'code' && activeBot && (
            <CodeViewer bot={activeBot} onBack={() => setActiveTab('editor')} />
          )}
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
