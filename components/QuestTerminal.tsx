import React, { useEffect, useState, useMemo } from 'react';

const QuestTerminal: React.FC = () => {
  const [v1, setV1] = useState('');
  const [v2, setV2] = useState('');
  const [msg, setMsg] = useState('СИСТЕМА: ОЖИДАНИЕ АВТОРИЗАЦИИ');
  const [bot, setBot] = useState('');

  const noise = useMemo(() => {
    const p = ["DATA_LEAK", "0x800421", "VOID", "MEM_ERR", "NULL_PTR"];
    return Array.from({ length: 20 }).map(() => ({
      t: p[Math.floor(Math.random() * p.length)],
      y: `${Math.random() * 100}%`,
      x: `${Math.random() * 100}%`,
      d: `${12 + Math.random() * 8}s`
    }));
  }, []);

  useEffect(() => {
    console.clear();
    console.log("%c [!] СИСТЕМНЫЙ ВЗЛОМ ОБНАРУЖЕН [!] ", "color:red;font-weight:bold;font-size:22px;");
    console.log("%c Декодируйте бинарный поток, затем примените сдвиг Цезаря (-3), чтобы найти стартовую команду. ", "color:#555;font-size:10px;");
    
    // Binary: "uhsdlu_prgxoh"
    console.log("LOG_01: 01110101 01101000 01110011 01100100 01101100 01110101 01011111 01110000 01110010 01100111 01111000 01101111 01101000");

    (window as any).repair_module = () => {
      const f = document.querySelectorAll('.c-p');
      const k = Array.from(f).map(e => ({ c: (e as HTMLElement).dataset.c || '', o: parseInt((e as HTMLElement).dataset.o || '0') })).sort((a, b) => a.o - b.o).map(p => p.c).join('');
      
      if (k === "Hjdvdosi3245") {
        console.log("%c [ПОТОК ВОССТАНОВЛЕН] ", "color:#0f0;font-weight:bold;");
        // Binary: "Kmgygrvl6578"
        console.log("LOG_02: 01001011 01101101 01100111 01111001 01100111 01110010 01110110 01101100 00110110 00110101 00110111 00111000");

        Object.defineProperty(window, k, {
          get: () => {
            console.log("%c УРОВЕНЬ_2: ДОСТУПЕН ", "color:#0f0;");
            // Binary: "hahfxwh_uhfryhub"
            console.log("LOG_03: 01101000 01100001 01101000 01100110 01111000 01110111 01101000 01011111 01110101 01101000 01100110 01110010 01111001 01101000 01110101 01100010");
            
            (window as any).execute_recovery = () => {
                console.log("%c ГЕНЕРАЦИЯ ФИНАЛЬНОГО ТОКЕНА... ", "color:#888;");
                // Binary: "aevlRq)bwymHz#e~lkGx"
                console.log("LOG_FINAL: 01100001 01100101 01110110 01101100 01010010 01110001 00101001 01100010 01110111 01111001 01101101 01001000 01111010 00100011 01100101 01111111 01101100 01101011 01000111 01111000");
                return "DECODE_LOG_FINAL_AND_ENTER_ON_PAGE";
            };
            return "AWAITING_EXECUTE_RECOVERY";
          },
          configurable: true
        });
        return "CORE_STABLE";
      }
      return "ACCESS_DENIED";
    };
  }, []);

  const handleAuth = (e: React.FormEvent) => {
    e.preventDefault();
    if (v2.trim() === "xbsiOn)ytvjEw#bihDu") {
      const b = [102, 115, 103, 104, 115, 103, 100, 112, 105, 103, 104, 100, 102, 98, 111, 116].map(c => String.fromCharCode(c)).join('');
      setBot(`@${b}`);
      setMsg("АВТОРИЗАЦИЯ УСПЕШНА.");
    } else {
      setMsg("ОШИБКА: КЛЮЧ НЕ ПРИНЯТ.");
    }
  };

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', overflow: 'hidden', position: 'relative' }}>
      
      {noise.map((p, i) => (
        <div key={i} style={{ position: 'absolute', top: p.y, left: p.x, color: '#001a00', fontSize: '10px', animation: `f ${p.d} linear infinite`, zIndex: 0 }}>
          {p.t}
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

      <div style={{ border: '1px solid #0f0', padding: '50px', background: '#050505', textAlign: 'center', width: '450px', zIndex: 1, boxShadow: '0 0 40px rgba(0,255,0,0.15)' }}>
        <h1 style={{ marginBottom: '30px', letterSpacing: '5px', fontSize: '22px' }}>VIRTUAL_OS_V12</h1>
        
        <form onSubmit={handleAuth} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <input type="text" placeholder="SESSION_UUID" style={{ background: '#000', border: '1px solid #003300', color: '#0f0', width: '100%', padding: '12px', outline: 'none' }} />
          <input type="text" value={v2} onChange={(e) => setV2(e.target.value)} placeholder="ENTER_DECODED_KEY" style={{ background: '#000', border: '1px solid #0f0', color: '#0f0', width: '100%', padding: '12px', outline: 'none', textAlign: 'center' }} />
          <button type="submit" style={{ background: '#0f0', color: '#000', border: 'none', padding: '15px', fontWeight: 'bold', cursor: 'pointer', letterSpacing: '2px' }}>ACCESS_KERNEL</button>
        </form>

        <div style={{ marginTop: '30px', minHeight: '60px' }}>
          <p style={{ fontSize: '14px', textShadow: '0 0 5px #0f0' }}>{msg}</p>
          {bot && <div style={{ border: '1px dashed #0f0', padding: '15px', marginTop: '15px', color: '#fff', background: 'rgba(0,255,0,0.05)' }}>
            TARGET_BOT: <span style={{color:'#0f0', fontWeight: 'bold'}}>{bot}</span>
          </div>}
        </div>
      </div>

      <style>{`
        @keyframes f { 0% { transform: translateY(110vh); } 100% { transform: translateY(-110vh); } }
      `}</style>
    </div>
  );
};

export default QuestTerminal;
