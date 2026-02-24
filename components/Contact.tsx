import React from 'react';

const Contacts: React.FC = () => {
  return (
    <div className="p-8 text-white bg-[#121212] rounded-3xl border border-zinc-800">
      <h1 className="text-2xl font-bold mb-6">Контакты и реквизиты</h1>
      <div className="space-y-4 text-zinc-400">
        <p><strong className="text-white">Продавец:</strong> Сазонов Виктор Александрович</p>
        <p><strong className="text-white">ИНН:</strong> 503818798300</p>
        <p><strong className="text-white">E-mail:</strong> vitechek.208@gmail.com</p>
        <p><strong className="text-white">Режим работы:</strong> Круглосуточно</p>
      </div>
    </div>
  );
};

export default Contacts;
