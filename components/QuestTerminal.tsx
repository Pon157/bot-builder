import React, { useEffect, useState, useMemo } from 'react';

const QuestTerminal: React.FC = () => {
  const [v1, setV1] = useState('');
  const [v2, setV2] = useState('');
  const [msg, setMsg] = useState('СИСТЕМА: ОЖИДАНИЕ АВТОРИЗАЦИИ');
  const [bot, setBot] = useState('');

  const backgroundNoise = useMemo(() => {
    const phrases = [
      "NULL_POINTER_DETECTED", "0x800421_FATAL", "MEM_LEAK_SECTOR_7G",
      "CORRUPTED_DATA_STREAM", "OVERRIDE_PROTOCOL_ACTIVE", "VOID_CORE_INITIALIZED",
      "ACCESS_DENIED_BY_KERNEL", "FRAGMENTED_MEMORY_DUMP", "DECRYPTING_LAYER_0...",
      "TARGET_ID: fsghsgdpighdfbot", "TRACING_ROUTE...", "HANDSHAKE_FAILED",
      "HASH_MISMATCH", "RECOVERY_MODE_ENABLED", "0x0000_SYSTEM_IDLE"
    ];
    return Array.from({ length: 30 }).map(() => ({
      text: phrases[Math.floor(Math.random() * phrases.length)],
      top: `${Math.random() * 100}%`,
      left: `${Math.random() * 100}%`,
      delay: `${Math.random() * 5}s`,
      duration: `${10 + Math.random() * 10}s`
    }));
  }, []);

  useEffect(() => {
    console.clear();
    console.log("%c [!] КРИТИЧЕСКИЙ СБОЙ ЯДРА [!] ", "color: #ff0000; font-weight: bold; font-size: 20px;");
    
    (window as any).repair_module = () => {
      const f = document.querySelectorAll('.c-p');
      const k = Array.from(f).map(e => ({ c: (e as HTMLElement).dataset.c || '', o: parseInt((e as HTMLElement).dataset.o || '0') })).sort((a, b) => a.o - b.o).map(p => p.c).join('');
      if (k === "Hjdvdosi3245") {
        Object.defineProperty(window, k, {
          get: () => {
            console.log("%c КЛЮЧ_1: rjqro9@{gjdl ", "color: #0f0; background: #222;");
            return "STAGE_1_OK";
          },
          configurable: true
        });
        (window as any).get_final_access = () => {
          console.log("%c ФИНАЛЬНЫЙ КОД: xbsiOn)ytvjEw#bihDu ", "color: #0f0; font-weight: bold;");
          return "TERMINATED";
        };
        return "Модуль восстановлен.";
      }
      return "ОШИБКА";
    };
  }, []);

  const check = (e: React.FormEvent) => {
    e.preventDefault();
    if (v2 === "xbsiOn)ytvjEw#bihDu") {
      const b = [102, 115, 103, 104, 115, 103, 100, 112, 105, 103, 104, 100, 102, 98, 111, 116].map(c => String.fromCharCode(c)).join('');
      setBot(`@${b}`);
      setMsg("ДОСТУП РАЗРЕШЕН.");
    } else {
      setMsg("ОШИБКА.");
    }
  };

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', overflow: 'hidden', position: 'relative' }}>
      
      {backgroundNoise.map((p, i) => (
        <div key={i} style={{ position: 'absolute', top: p.top, left: p.left, color: '#002200', fontSize: '10px', whiteSpace: 'nowrap', opacity: 0.5, animation: `float ${p.duration} linear infinite`, animationDelay: p.delay, userSelect: 'none', zIndex: 0 }}>
          {p.text}
        </div>
      ))}

      <div className="c-p" data-o="8" data-c="i" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="1" data-c="H" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="12" data-c="5" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="2" data-c="j" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="3" data-c="d" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="4" data-c="v" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="5" data-c="d" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="6" data-c="o" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="7" data-c="s" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="9" data-c="3" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="10" data-c="2" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="11" data-c="4" style={{ display: 'none' }}></div>

      <div style={{ border: '1px solid #0f0', padding: '40px', background: '#050505', textAlign: 'center', width: '400px', position: 'relative', zIndex: 1 }}>
        <h2 style={{ marginBottom: '20px', letterSpacing: '2px' }}>CORE_INTERFACE_V10</h2>
        
        <form onSubmit={check} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label style={{ fontSize: '10px', display: 'block', marginBottom: '5px' }}>ЛОКАЛЬНЫЙ ТОКЕН (ФЕЙК)</label>
            <input 
              type="text" 
              value={v1}
              onChange={(e) => { setV1(e.target.value); setMsg("ПРОВЕРКА..."); }}
              style={{ background: '#000', border: '1px solid #004400', color: '#0f0', width: '100%', padding: '10px', outline: 'none' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '10px', display: 'block', marginBottom: '5px' }}>МАГИСТРАЛЬНЫЙ КЛЮЧ</label>
            <input 
              type="text" 
              value={v2}
              onChange={(e) => setV2(e.target.value)}
              placeholder="Вставьте код..."
              style={{ background: '#000', border: '1px solid #0f0', color: '#0f0', width: '100%', padding: '10px', outline: 'none' }}
            />
          </div>

          <button type="submit" style={{ background: '#0f0', color: '#000', border: 'none', padding: '10px', fontWeight: 'bold', cursor: 'pointer' }}>
            ДЕШИФРОВАТЬ
          </button>
        </form>

        <div style={{ marginTop: '20px', minHeight: '40px' }}>
          <p style={{ fontSize: '12px', color: msg.includes('ОШИБКА') ? 'red' : '#0f0' }}>{msg}</p>
          {bot && (
            <div style={{ marginTop: '10px', padding: '10px', border: '1px dashed #0f0', color: '#fff' }}>
              ЦЕЛЬ НАЙДЕНА: <span style={{ fontWeight: 'bold', color: '#0f0' }}>{bot}</span>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes float {
          0% { transform: translateY(0) translateX(0); opacity: 0; }
          10% { opacity: 0.5; }
          90% { opacity: 0.5; }
          100% { transform: translateY(-100vh) translateX(${Math.random() > 0.5 ? '50px' : '-50px'}); opacity: 0; }
        }
      `}</style>
    </div>
  );
};

export default QuestTerminal;
