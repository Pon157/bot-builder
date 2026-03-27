// components/QuestTerminal.tsx
import React, { useEffect } from 'react';

const QuestTerminal: React.FC = () => {
  const secretEncoded = "SHpkdmRvc2kzMjQ1"; // Base64 от Hjdvdosi3245

  useEffect(() => {
    // 1. Засоряем консоль
    for (let i = 0; i < 20; i++) {
      console.log(`%c [SYSTEM] Проверка сектора ${i}... OK`, "color: #333");
    }

    // 2. Выводим настоящий ключ через 3 секунды
    const timer = setTimeout(() => {
      console.log("%c [!] ВЗЛОМ УСПЕШЕН [!] ", "background: #222; color: #00ff00; font-weight: bold;");
      console.log(`%c КОД ДОСТУПА: ${atob(secretEncoded)}`, "color: #00ff00; font-size: 16px;");
    }, 3000);

    return () => clearTimeout(timer);
  }, []);

  const handleFakeClick = () => {
    const out = document.getElementById('q-output');
    if (out) out.innerText = "> Error: Physical key required.";
  };

  return (
    <div style={{ backgroundColor: '#000', color: '#0f0', height: '100vh', fontFamily: 'monospace', padding: '40px' }}>
      <div style={{ border: '1px solid #0f0', padding: '20px', maxWidth: '600px', margin: 'auto' }}>
        <h2>REMOTE_TERMINAL_V4</h2>
        <p>> Состояние: <span style={{color: 'red'}}>ОЖИДАНИЕ ВВОДА</span></p>
        <p>> Обнаружена зашифрованная переменная .env.local</p>
        
        <button 
          onClick={handleFakeClick}
          style={{ background: '#0f0', color: '#000', border: 'none', padding: '10px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          FORCE_CONNECT
        </button>
        <div id="q-output" style={{ marginTop: '20px', color: '#555' }}></div>
        
        {/* Части кода спрятаны в атрибутах для тех, кто смотрит элементы */}
        <span data-part="1" style={{opacity: 0}}>Hjdv</span>
        <span data-part="2" style={{opacity: 0}}>dosi3245</span>
      </div>
      <div style={{ textAlign: 'center', marginTop: '20px', color: '#111' }}>
        Hint: DevTools Console (F12)
      </div>
    </div>
  );
};

export default QuestTerminal;
