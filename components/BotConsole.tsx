
import React, { useEffect, useRef } from 'react';
import { MessageLog } from '../types';
import { Terminal, RefreshCw, Info, AlertCircle, ArrowLeft, ArrowRight, Zap } from 'lucide-react';

interface BotConsoleProps {
  logs: MessageLog[];
}

const BotConsole: React.FC<BotConsoleProps> = ({ logs }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  const sortedLogs = [...(logs || [])].sort((a, b) => b.timestamp - a.timestamp);

  const getLogIcon = (type: string) => {
    switch (type) {
      case 'error': return <AlertCircle className="w-3 h-3 text-red-500" />;
      case 'info': return <Info className="w-3 h-3 text-blue-500" />;
      case 'incoming': return <ArrowLeft className="w-3 h-3 text-emerald-500" />;
      case 'outgoing': return <ArrowRight className="w-3 h-3 text-purple-500" />;
      case 'system': return <Zap className="w-3 h-3 text-amber-500" />;
      default: return <Terminal className="w-3 h-3 text-zinc-500" />;
    }
  };

  return (
    <div className="bg-[#0a0a0a] border border-zinc-800 rounded-3xl overflow-hidden flex flex-col h-[500px] shadow-2xl">
      <div className="bg-[#111] px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <Terminal className="w-4 h-4 text-blue-500" />
          </div>
          <div>
            <span className="text-[10px] font-black uppercase tracking-widest text-white">System Console</span>
            <p className="text-[8px] text-zinc-500 font-bold uppercase mt-0.5">Real-time bot events stream</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
            <span className="text-[8px] text-zinc-600 font-mono hidden sm:inline">BUFFER: {sortedLogs.length}/50</span>
            <button className="p-2 hover:bg-white/5 rounded-lg transition-colors text-zinc-500 hover:text-white">
                <RefreshCw className="w-3.5 h-3.5" />
            </button>
        </div>
      </div>
      
      <div 
        ref={scrollRef}
        className="flex-1 p-4 sm:p-6 font-mono text-[11px] overflow-y-auto space-y-2 no-scrollbar bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-zinc-900/20 via-transparent to-transparent"
      >
        {sortedLogs.length === 0 ? (
          <div className="text-zinc-800 flex flex-col items-center justify-center h-full space-y-4">
            <div className="w-12 h-12 rounded-full border border-dashed border-zinc-800 flex items-center justify-center">
                <Terminal className="w-6 h-6 opacity-20" />
            </div>
            <p className="uppercase tracking-[0.2em] text-[10px] font-black opacity-30">Waiting for live data...</p>
          </div>
        ) : (
          sortedLogs.map(log => (
            <div key={log.id} className="group flex gap-4 items-start py-2 border-b border-white/[0.02] last:border-0 hover:bg-white/[0.01] transition-colors rounded-lg px-2">
              <span className="text-zinc-600 shrink-0 text-[9px] tabular-nums mt-1 w-14">
                {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <div className="flex-1 flex gap-3 items-start">
                <div className="mt-1 shrink-0">{getLogIcon(log.type)}</div>
                <div className="flex-1">
                    <span className={`
                    inline-block px-1.5 py-0.5 rounded-md text-[8px] font-black uppercase tracking-wider mr-3 mb-1
                    ${log.type === 'error' ? 'bg-red-500/10 text-red-500' : ''}
                    ${log.type === 'info' ? 'bg-blue-500/10 text-blue-500' : ''}
                    ${log.type === 'incoming' ? 'bg-emerald-500/10 text-emerald-500' : ''}
                    ${log.type === 'outgoing' ? 'bg-purple-500/10 text-purple-500' : ''}
                    ${log.type === 'system' ? 'bg-amber-500/10 text-amber-500' : ''}
                    `}>
                    {log.type}
                    </span>
                    <span className={`
                    ${log.type === 'error' ? 'text-red-400' : 'text-zinc-400'}
                    leading-relaxed break-words block sm:inline text-[12px]
                    `}>
                    {log.text}
                    </span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default BotConsole;
