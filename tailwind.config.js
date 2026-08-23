/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{html,ts}',
    './node_modules/preline/dist/*.js',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4ff',
          100: '#dfe9fe',
          200: '#c7d8fe',
          300: '#a4bdfc',
          400: '#7e9bf8',
          500: '#6178f2',
          600: '#4555e6',
          700: '#3742cb',
          800: '#3038a3',
          900: '#2d3582',
        },
      },
    },
  },
  plugins: [],
}
