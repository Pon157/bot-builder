/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./*.tsx",            // Файлы в корне (App.tsx, index.tsx)
    "./components/**/*.tsx", // Файлы в папке компонентов
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
