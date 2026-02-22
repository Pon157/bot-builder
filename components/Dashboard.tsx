import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BotConfig } from '../types';
import { MessageSquare, Plus, Globe, ExternalLink, ChevronRight } from 'lucide-react';

interface DashboardProps {
  bots: BotConfig[];
  onSelectBot: (id: string) => void;
  onAddBot: () => void;
  onNavigate?: (path: string) => void;
}

// Мини-тип для превью чат-сайтов
interface ChatSitePreview {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  config?: { primaryColor?: string; bgColor?: string; logoText?: string };
}

const Dashboard: React.FC<DashboardProps> = ({ bots, onSelectBot, onAddBot }) => {
  const navigate = useNavigate();
  const [isFaqOpen, setIsFaqOpen] = useState(false);
  const [chatSites, setChatSites] = useState<ChatSitePreview[]>([]);

  const totalUsers = bots.reduce((acc, b) => acc + (b.connectedUsers?.length || 0), 0);
  const totalMessages = bots.reduce((acc, b) => acc + (b.stats?.totalMessages || 0), 0);
  const activeBots = bots.filter(b => b.status === 'RUNNING').length;

  // Загружаем чат-сайты владельца (если есть userId в storage)
  useEffect(() => {
    const loadSites = async () => {
      try {
        const userStr = localStorage.getItem('active_session_user');
        if (!userStr) return;
        const u = JSON.parse(userStr);
        const res = await fetch(`/api/chat/sites/owner/${u.id}`);
        const data = await res.json();
        setChatSites(Array.isArray(data) ? data.slice(0, 6) : []);
      } catch { }
    };
    loadSites();
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in duration-500 relative">
      <header>
        <h1 className="text-4xl font-black mb-2 text-white">Управление узлами</h1>
        <p className="text-zinc-500 text-sm font-medium">Централизованный контроль вашей сети Telegram-ботов.</p>
      </header>

      {/* Сетка статистики + FAQ */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800">
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mb-4">Активные инстансы</p>
            <div className="flex items-end gap-2">
                <p className="text-5xl font-black text-white">{activeBots}</p>
                <p className="text-zinc-700 font-bold mb-1">/ {bots.length}</p>
            </div>
        </div>
        
        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800">
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mb-4">Общий охват (Users)</p>
            <p className="text-5xl font-black text-blue-500">{totalUsers.toLocaleString()}</p>
        </div>

        <div className="bg-[#111] p-8 rounded-[2.5rem] border border-zinc-800">
            <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest mb-4">Всего транзакций</p>
            <p className="text-5xl font-black text-white">{totalMessages.toLocaleString()}</p>
        </div>

        {/* КАРТОЧКА FAQ */}
        <div 
          onClick={() => setIsFaqOpen(true)}
          className="bg-blue-600/10 p-8 rounded-[2.5rem] border border-blue-500/20 hover:border-blue-500/50 transition-all cursor-pointer group flex flex-col justify-between"
        >
            <p className="text-blue-500 text-[10px] font-bold uppercase tracking-widest mb-4">Помощь и FAQ</p>
            <div className="flex items-center justify-between">
                <p className="text-xl font-black text-white leading-tight">Документация системы</p>
                <div className="bg-blue-500 p-2 rounded-xl group-hover:scale-110 transition-transform text-white shrink-0 ml-4">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
            </div>
        </div>
      </div>

{/* Секция Ваших ботов */}
<section className="space-y-6">
  <div className="flex items-center justify-between">
      <h2 className="text-xl font-black text-white">Ваши инстансы</h2>
      <button onClick={onAddBot} className="text-blue-500 text-xs font-bold uppercase tracking-widest hover:underline">+ Создать новый</button>
  </div>
  
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {bots.map(bot => (
          <div 
              key={bot.id}
              className="bg-[#111] border border-zinc-800 rounded-[2.5rem] p-8 hover:border-blue-500/50 transition-all cursor-pointer group relative"
              onClick={() => onSelectBot(bot.id)}
          >
              <div className="flex justify-between items-start mb-6">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${bot.status === 'RUNNING' ? 'bg-blue-500/10 text-blue-500' : 'bg-zinc-900 text-zinc-600'}`}>
                      {bot.platform === 'vk' ? (
                        <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M13.162 18.994c-6.098 0-9.57-4.172-9.714-11.107h3.047c.101 5.088 2.339 7.243 4.116 7.688V7.887H13.5v4.39c1.673-.18 3.514-2.185 4.102-4.39h2.903a9.408 9.408 0 01-3.763 5.483 9.771 9.771 0 014.436 5.624h-3.235c-.636-1.992-2.228-3.528-4.557-3.757v3.757h-.224z"/>
                        </svg>
                      ) : bot.platform === 'poster' ? (
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      ) : bot.platform === 'randomizer' ? (
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M16 3h5m0 0v5m0-5l-6 6M5 3a2 2 0 00-2 2v1c0 8.284 6.716 15 15 15h1a2 2 0 002-2v-1m-8-5l3 3 3-3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      ) : (
                        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      )}
                  </div>
                  <div className="flex items-center gap-2">
                      <span className="bg-zinc-800/80 text-zinc-500 text-[8px] font-black px-2.5 py-1 rounded-lg uppercase tracking-wider">
                        {bot.platform === 'vk' ? 'VK' : bot.platform === 'poster' ? 'Постинг' : bot.platform === 'randomizer' ? 'Лотерея' : 'Telegram'}
                      </span>
                      <span className={`text-[9px] px-3 py-1 rounded-full font-black uppercase ${bot.status === 'RUNNING' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-800 text-zinc-500'}`}>
                          {bot.status}
                      </span>
                  </div>
              </div>
              
              <h3 className="text-xl font-black text-white mb-2 group-hover:text-blue-500 transition-colors">{bot.name}</h3>
              
              <div className="flex items-center gap-6 mt-6 pt-6 border-t border-zinc-800/50">
                  <div className="text-center">
                      <p className="text-lg font-black text-white">{bot.connectedUsers?.length || 0}</p>
                      <p className="text-[8px] text-zinc-600 uppercase font-bold">Users</p>
                  </div>
                  <div className="text-center">
                      <p className="text-lg font-black text-white">{bot.stats?.totalMessages || 0}</p>
                      <p className="text-[8px] text-zinc-600 uppercase font-bold">Msgs</p>
                  </div>
              </div>
          </div>
      ))}
  </div>
</section>

{/* ─── Секция чат-платформ ─── */}
<section className="space-y-5">
  <div className="flex items-center justify-between">
    <div>
      <h2 className="text-xl font-black text-white">Чат-платформы</h2>
      <p className="text-zinc-600 text-xs font-medium mt-0.5">Публичные мессенджеры с регистрацией пользователей</p>
    </div>
    <button
      onClick={() => navigate('/chatplatform')}
      className="flex items-center gap-1.5 text-blue-500 text-xs font-bold uppercase tracking-widest hover:underline"
    >
      Управление <ChevronRight className="w-3.5 h-3.5" />
    </button>
  </div>

  {chatSites.length === 0 ? (
    <div
      className="border-2 border-dashed border-zinc-800 rounded-[2.5rem] p-10 text-center cursor-pointer hover:border-blue-500/30 transition-all group"
      onClick={() => navigate('/chatplatform')}
    >
      <MessageSquare className="w-8 h-8 text-zinc-700 group-hover:text-blue-500/50 mx-auto mb-3 transition-colors" />
      <p className="text-zinc-600 text-xs font-black uppercase tracking-widest mb-2">Нет чат-сайтов</p>
      <span className="text-blue-500 text-xs font-bold hover:underline inline-flex items-center gap-1">
        <Plus className="w-3.5 h-3.5" /> Создать первый
      </span>
    </div>
  ) : (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      {chatSites.map(site => {
        const primary = site.config?.primaryColor || '#6366f1';
        const bg = site.config?.bgColor || '#09090b';
        const siteUrl = `/chat/${site.slug}`;
        return (
          <div key={site.id}
            className="bg-[#111] border border-zinc-800 rounded-[2rem] overflow-hidden hover:border-zinc-700 transition-all group cursor-pointer"
            onClick={() => navigate('/chatplatform')}>
            {/* Превью шапки сайта */}
            <div className="h-14 flex items-center px-5 gap-2" style={{ background: bg }}>
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: primary }} />
              <span className="font-black text-sm truncate" style={{ color: primary }}>
                {site.config?.logoText || site.name}
              </span>
              <div className="ml-auto flex gap-1">
                {[0, 1, 2].map(i => <div key={i} className="w-1.5 h-1.5 rounded-full bg-white/10" />)}
              </div>
            </div>
            <div className="p-5 flex items-center justify-between">
              <div>
                <p className="text-white font-black text-sm group-hover:text-blue-400 transition-colors">{site.name}</p>
                <p className="text-zinc-600 text-[9px] font-mono mt-0.5">/chat/{site.slug}</p>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${site.is_active ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
                <a href={siteUrl} target="_blank" rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 transition-all">
                  <ExternalLink className="w-3 h-3 text-zinc-500 hover:text-white transition-colors" />
                </a>
              </div>
            </div>
          </div>
        );
      })}
      {/* Плашка «Добавить ещё» */}
      <div
        onClick={() => navigate('/chatplatform')}
        className="border-2 border-dashed border-zinc-800 rounded-[2rem] p-8 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-blue-500/30 transition-all group">
        <Plus className="w-6 h-6 text-zinc-700 group-hover:text-blue-500/50 transition-colors" />
        <span className="text-zinc-600 text-[9px] font-black uppercase tracking-widest">Новый сайт</span>
      </div>
    </div>
  )}
</section>

      {/* OVERLAY: Просмотр PDF документа */}
      {isFaqOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-12 animate-in fade-in duration-300">
          {/* Фон с размытием */}
          <div 
            className="absolute inset-0 bg-black/90 backdrop-blur-xl" 
            onClick={() => setIsFaqOpen(false)} 
          />
          
          <div className="relative w-full max-w-6xl h-full bg-[#0a0a0a] border border-zinc-800 rounded-[3rem] overflow-hidden flex flex-col shadow-2xl animate-in zoom-in-95 duration-300">
            {/* Шапка модалки */}
            <div className="flex items-center justify-between p-8 border-b border-zinc-800 bg-[#111]">
              <div>
                <h3 className="text-2xl font-black text-white">Документация FAQ</h3>
                <p className="text-zinc-500 text-xs font-medium uppercase tracking-widest mt-1">Справочное руководство системы</p>
              </div>
              <div className="flex items-center gap-4">
                <a 
                  href="/FAQwithVK.pdf" 
                  download 
                  className="hidden md:flex items-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-white px-5 py-2.5 rounded-2xl text-xs font-bold transition-all"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  Скачать PDF
                </a>
                <button 
                  onClick={() => setIsFaqOpen(false)}
                  className="p-3 hover:bg-zinc-800 rounded-2xl text-zinc-500 hover:text-white transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" strokeWidth="2" strokeLinecap="round"/></svg>
                </button>
              </div>
            </div>
            
            {/* Контент с PDF */}
            <div className="flex-1 bg-[#050505] relative">
              <iframe 
                src="/FAQwithVK.pdf#toolbar=0&navpanes=0" 
                className="w-full h-full border-none"
                title="FAQ Documentation"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
