/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#f5f7f7',
        accent: '#a9f0df',
      },
      boxShadow: {
        glass: '0 24px 80px rgba(0, 0, 0, 0.34)',
      },
    },
  },
  plugins: [],
}
