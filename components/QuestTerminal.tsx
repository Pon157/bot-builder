import React, { useEffect, useState } from 'react';

const QuestTerminal: React.FC = () => {
  const [s, setS] = useState<string>('ERR: 0x800421');

  useEffect(() => {
    console.clear();
    console.log("%c КРИТИЧЕСКИЙ СБОЙ: СЕКТОР ПАМЯТИ ПОВРЕЖДЕН ", "color:red;font-weight:bold;");
    
    (window as any).repair_module = () => {
      const f = document.querySelectorAll('.c-p');
      const k = Array.from(f).map(e => ({ c: (e as HTMLElement).dataset.c || '', o: parseInt((e as HTMLElement).dataset.o || '0') })).sort((a, b) => a.o - b.o).map(p => p.c).join('');

      if (k === "Hjdvdosi3245") {
        Object.defineProperty(window, k, {
          get: () => {
            const c1 = [2, 11, 2, 1, 31, 88, 51, 8, 23, 11, 23, 31];
            const m = "pass";
            const r1 = c1.map((b, i) => String.fromCharCode(b ^ m.charCodeAt(i % m.length))).join('');
            console.log(`%c ЭТАП 1 ЗАВЕРШЕН. КЛЮЧ: ${r1}`, "color:#0f0;font-weight:bold;");
            console.log("%c ТРЕБУЕТСЯ АКТИВАЦИЯ ПОТОКА: 'get_final_access()'", "color:#888;");
            return "STAGE_1_OK";
          },
          configurable: true
        });

        (window as any).get_final_access = () => {
          const c2 = [27, 13, 1, 12, 16, 24, 16, 26, 27, 4, 15, 26, 1, 26, 1, 16, 27, 13, 27, 3];
          const m2 = "core_v9";
          const r2 = c2.map((b, i) => String.fromCharCode(b ^ m2.charCodeAt(i % m2.length))).join('');
          console.log("%c [!] ДОСТУП ВОССТАНОВЛЕН [!] ", "background:#0f0;color:#000;padding:5px;");
          console.log(`%c ФИНАЛЬНЫЙ КОД: ${r2}`, "font-size:16px;color:#0f0;font-weight:bold;");
          return "TERMINATED";
        };
        return `Слой [${k}] активен.`;
      }
      return "ОШИБКА_ЦЕЛОСТНОСТИ";
    };
    return () => { delete (window as any).repair_module; };
  }, []);

  const g_b = () => {
    // Собираем fsghsgdpighdfbot из кодов символов, чтобы не палить в поиске
    return [102, 115, 103, 104, 115, 103, 100, 112, 105, 103, 104, 100, 102, 98, 111, 116].map(c => String.fromCharCode(c)).join('');
  };

  return (
    <div style={{ backgroundColor: '#000', color: '#003300', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', overflow: 'hidden', position: 'relative' }}>
      
      <div className="c-p" data-o="8" data-c="i" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="3" data-c="d" style={{ opacity: 0 }}></div>
      <div className="c-p" data-o="12" data-c="5" style={{ position: 'absolute', left: '-2000px' }}></div>
      <div className="c-p" data-o="1" data-c="H" style={{ width: 0, height: 0, overflow: 'hidden' }}></div>
      <div className="c-p" data-o="6" data-c="o" style={{ visibility: 'hidden' }}></div>
      <div className="c-p" data-o="10" data-c="2" style={{ color: 'transparent' }}></div>
      <div className="c-p" data-o="4" data-c="v" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="2" data-c="j" style={{ fontSize: 0 }}></div>
      <div className="c-p" data-o="11" data-c="4" style={{ display: 'none' }}></div>
      <div className="c-p" data-o="7" data-c="s" style={{ opacity: 0 }}></div>
      <div className="c-p" data-o="5" data-c="d" style={{ position: 'fixed', top: '-100px' }}></div>
      <div className="c-p" data-o="9" data-c="3" style={{ display: 'none' }}></div>

      <div style={{ border: '1px solid #001100', padding: '60px', textAlign: 'center', background: '#000' }}>
        <h2 style={{ letterSpacing: '12px', color: '#004400' }}>SYSTEM_KERNEL</h2>
        <input 
          type="text" 
          placeholder="..."
          style={{ background: 'transparent', border: '1px solid #002200', color: '#004400', textAlign: 'center', padding: '5px', outline: 'none', marginTop: '20px' }}
          onChange={() => setS('SIGNAL_INTERRUPTED')}
        />
        <p style={{ fontSize: '9px', marginTop: '20px' }}>{s}</p>
      </div>

      <div style={{ position: 'fixed', bottom: '5px', left: '5px', fontSize: '8px', opacity: 0.2 }}>
        ID: {g_b()}
      </div>
    </div>
  );
};

export default QuestTerminal;
