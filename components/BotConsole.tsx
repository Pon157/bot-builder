import React, { useEffect, useState, useMemo } from 'react';
import { 
  RefreshCw, AlertCircle, ShieldAlert, Zap, Info, 
  ShieldX, LayoutList, TerminalSquare 
} from 'lucide-react';
import { api } from '../services/apiService';

interface BotConsoleProps {
  botId: string;
}

interface SystemEvent {
  time: string;
  type: 'error' | 'warning' | 'info' | 'critical';
  title: string;
  description: string;
  raw: string;
}

const BotConsole: React.FC<BotConsoleProps> = ({ botId }) => {
  const [logs, setLogs] = useState<string>('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchLogs = async () => {
    setIsRefreshing(true);
    const data = await api.getBotLogs(botId);
    setLogs(data);
    setIsRefreshing(false);
  };

  useEffect(() => {
    fetchLogs();
    const timer = setInterval(fetchLogs, 10000); // Раз в 10 секунд достаточно для ивентов
    return () => clearInterval(timer);
  }, [botId]);

  const systemEvents = useMemo(() => {
    if (!logs) return [];

    const lines = logs.split('\n').filter(line => line.trim());
    const events: SystemEvent[] = [];

    lines.forEach(line => {
      const timeMatch = line.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
      const time = timeMatch ? timeMatch[1].split(' ')[1] : '--:--';

      // 1. Критические ошибки прав
      if (line.includes('not enough rights to create topics')) {
        events.push({
          time, type: 'critical', title: 'Ошибка прав: Темы',
          description: 'Бот не может создавать темы. Дайте права "Управление темами" в группе.',
          raw: line
        });
      }
      else if (line.includes('is not an administrator')) {
        events.push({
          time, type: 'critical', title: 'Бот не администратор',
          description: 'Бот потерял права админа или не был назначен. Функции ограничены.',
          raw: line
        });
      }
      // 2. Ошибки взаимодействия
      else if (line.includes('Forbidden: bot was blocked by the user')) {
        events.push({
          time, type: 'warning', title: 'Бот заблокирован',
          description: 'Пользователь отправил бота в бан. Рассылка ему прекращена.',
          raw: line
        });
      }
      else if (line.includes('TelegramRetryAfter')) {
        const sec = line.match(/after (\d+)/)?.[1] || '?';
        events.push({
          time, type: 'warning', title: 'Flood Control',
          description: `Превышен лимит запросов. Пауза на ${sec} сек.`,
          raw: line
        });
      }
      // 3. Системные статусы
      else if (line.includes('[*] Бот') && line.includes('запущен')) {
        events.push({
          time, type: 'info', title: 'Запуск системы',
          description: 'Все модули бота успешно инициализированы и запущены.',
          raw: line
        });
      }
      else if (line.includes('ERROR') || line.includes('Exception')) {
        // Общая ошибка, если не попала под фильтры выше
        events.push({
          time, type: 'error', title: 'Ошибка исполнения',
          description: 'Произошла непредвиденная ошибка в коде ядра.',
          raw: line
        });
      }
    });

    return events.reverse(); // Свежие ивенты сверху
  }, [logs]);

  return (
    <div className="flex flex-col h-full bg-zinc-950 border border-zinc-800 rounded-3xl overflow-hidden shadow-2xl">
      {/* Header */}
      <div className="px-6 py-5 border-b border-zinc-800 bg-zinc-900/40 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-500/10 rounded-2xl flex items-center justify-center border border-blue-500/20">
            <LayoutList className="w-5 h-5 text-blue-500" />
          </div>
          <div>
            <h2 className="text-sm font-black text-zinc-100 uppercase tracking-[0.1em]">Системный журнал</h2>
            <div className="flex items-center gap-2">
              <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <p className="text-[10px] text-zinc-500 font-bold uppercase">Мониторинг активен</p>
            </div>
          </div>
        </div>
        
        <button 
          onClick={fetchLogs}
          disabled={isRefreshing}
          className={`p-2.5 bg-zinc-800/50 hover:bg-zinc-800 rounded-xl transition-all border border-zinc-700/50 ${isRefreshing ? 'animate-spin text-blue-500' : 'text-zinc-400'}`}
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Events List */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
        {systemEvents.length > 0 ? (
          systemEvents.map((ev, i) => (
            <div 
              key={i} 
              className={`group p-4 rounded-2xl border transition-all hover:scale-[1.01] ${
                ev.type === 'critical' || ev.type === 'error' 
                  ? 'bg-rose-500/5 border-rose-500/20 shadow-sm shadow-rose-500/5' 
                  : ev.type === 'warning' 
                  ? 'bg-amber-500/5 border-amber-500/20' 
                  : 'bg-zinc-900/30 border-zinc-800/50'
              }`}
            >
              <div className="flex items-start gap-4">
                <div className={`mt-1 p-2.5 rounded-xl ${
                  ev.type === 'critical' || ev.type === 'error' ? 'text-rose-500 bg-rose-500/10' :
                  ev.type === 'warning' ? 'text-amber-500 bg-amber-500/10' : 'text-blue-500 bg-blue-500/10'
                }`}>
                  {ev.type === 'critical' ? <ShieldX className="w-5 h-5" /> : 
                   ev.type === 'error' ? <AlertCircle className="w-5 h-5" /> :
                   ev.type === 'warning' ? <ShieldAlert className="w-5 h-5" /> : <Info className="w-5 h-5" />}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1.5">
                    <h4 className={`text-xs font-black uppercase tracking-wider truncate ${
                      ev.type === 'critical' || ev.type === 'error' ? 'text-rose-400' :
                      ev.type === 'warning' ? 'text-amber-400' : 'text-zinc-200'
                    }`}>
                      {ev.title}
                    </h4>
                    <span className="text-[10px] font-mono text-zinc-600 tabular-nums">
                      [{ev.time}]
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-400 font-medium leading-relaxed">
                    {ev.description}
                  </p>
                  
                  <div className="mt-3 pt-3 border-t border-white/[0.03] opacity-0 group-hover:opacity-100 transition-opacity">
                    <code className="text-[9px] text-zinc-600 font-mono break-all line-clamp-1">
                      {ev.raw}
                    </code>
                  </div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="h-full flex flex-col items-center justify-center space-y-4 opacity-20">
            <TerminalSquare className="w-16 h-16 text-zinc-600" />
            <div className="text-center">
              <p className="text-xs font-black uppercase tracking-[0.2em] text-zinc-500">Журнал пуст</p>
              <p className="text-[10px] text-zinc-600 font-bold uppercase mt-1">Ожидание первого события...</p>
            </div>
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div className="px-6 py-4 bg-zinc-900/20 border-t border-zinc-800">
        <p className="text-[9px] text-zinc-600 font-bold uppercase tracking-widest text-center">
          Фильтрация: <span className="text-zinc-400">Только критические ошибки и системные уведомления</span>
        </p>
      </div>
    </div>
  );
};

export default BotConsole;
