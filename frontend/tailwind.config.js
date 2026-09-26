/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // El salón está oscuro y el proyector pierde brillo: fondo bien oscuro
        // y texto blanco. El acento tiene que leerse en un celular con el
        // brillo bajo y en una pared a tres metros.
        //
        // Estilo de iOS: vidrio translúcido sobre fondo negro y los colores de
        // sistema de Apple en modo oscuro. Sin degradés. El blur vive en
        // index.css, sobre .bg-panel; por eso `panel` y `borde` son blancos con
        // transparencia y no grises sólidos.
        fondo: "#000000",
        panel: "rgb(255 255 255 / 0.08)",
        borde: "rgb(255 255 255 / 0.16)",
        // Campos y códigos: un hundido oscuro dentro del vidrio.
        hundido: "rgb(118 118 128 / 0.24)",
        acento: "#0A84FF", // systemBlue
        rojo: "#FF453A", // systemRed
        verde: "#30D158", // systemGreen
        naranja: "#FF9F0A", // systemOrange
        tenue: "rgb(235 235 245 / 0.6)", // secondaryLabel
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
