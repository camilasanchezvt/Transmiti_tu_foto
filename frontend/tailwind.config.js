/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // El salón está oscuro y el proyector pierde brillo: fondo bien oscuro
        // y texto blanco. El acento tiene que leerse en un celular con el
        // brillo bajo y en una pared a tres metros.
        fondo: "#0b0b0f",
        panel: "#16161d",
        borde: "#2a2a35",
        acento: "#f4a261",
        tenue: "#9a9aa8",
      },
      minHeight: {
        // El brief pide botones de 56 px como mínimo: se usan con una mano y
        // con una copa en la otra.
        boton: "56px",
      },
    },
  },
  plugins: [],
};
