import React, { useEffect } from 'react';

const QuestTerminal: React.FC = () => {
  // Название функции = раскодированный код
  const secretKey = "Hjdvdosi3245";
  // То, что он получит в итоге
  const finalPrize = "TG_MASTER_QUEST_777";

  useEffect(() => {
    // 1. Очищаем консоль при загрузке для чистоты
    console.clear();

    // 2. Выводим зашифрованную подсказку
    console.log("%c [CORE]: Обнаружен зашифрованный вызов системы. ", "color: #0f0; font-weight: bold;");
    console.log("BASE64_FRAGMENT: %c SHpkdmRvc2kzMjQ1 ", "background: #222; color: #ff0; padding: 2px;");
    console.log("%c Подсказка: Раскодируй фрагмент и исполни его как команду здесь же. ", "color: #666; font-style: italic;");

    // 3. Магия: объявляем функцию в глобальном объекте window
    // Теперь, если юзер введет Hjdvdosi3245() в консоль, она сработает
    (window as any)[secretKey] = () => {
      console.log("%c [SUCCESS]: Доступ к ядру разрешен! ", "color: white; background: green; padding: 5px;");
      console.log(`%c ВАШ ФИНАЛЬНЫЙ КОД ДЛЯ БОТА: ${finalPrize}`, "font-size: 16px; font-weight: bold; color: #0f0;");
      return "--- Конец связи ---";
    };

    // 4. Чтобы юзер не получил ошибку, если введет без скобок (просто Hjdvdosi3245)
    // Мы можем переопределить toString или просто оставить как функцию.
    // Но лучше научить его вызывать функцию.

    return () => {
      // Подчищаем за собой при уходе со страницы
      delete (window as any)[secretKey];
    };
  }, []);

  return (
    <div style={{ backgroundColor: '#050505', color: '#00ff41', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace' }}>
      <div style={{ border: '2px solid #00ff41', padding: '30px', textAlign: 'center', boxShadow: '0 0 20px rgba(0, 255, 65, 0.2)' }}>
        <h1 style={{ letterSpacing: '5px' }}>TERMINAL_ACCESS</h1>
        <p style={{ color: '#008f11' }}>{"> "} Используйте консоль разработчика (F12) для взаимодействия с ядром.</p>
        <div style={{ marginTop: '20px', fontSize: '12px', opacity: 0.5 }}>
          [ Waiting for external command input... ]
        </div>
      </div>
    </div>
  );
};

export default QuestTerminal;
