/** @type {import('tailwindcss').Config} */

// Los colores viven como variables CSS en src/index.css, una paleta por tema
// (data-tema="oscuro" | "claro" en <html>). Acá sólo se nombran.
//
// Formato de las variables: "R G B", sin la función rgb(). Así Tailwind puede
// ponerle opacidad: bg-acento/15, text-texto/60, shadow-sombra/40.
//
// Los que ya son translúcidos por diseño (panel, borde, hundido, tenue, barra,
// velo, pulsado, elegido, hoja) traen su propia opacidad en una variable "-alfa",
// distinta en cada tema: el vidrio de noche no es el mismo que el de día. A
// esos no se les pone /NN.
const color = (nombre) => `rgb(var(--${nombre}) / <alpha-value>)`;
const translucido = (nombre) => `rgb(var(--${nombre}) / var(--${nombre}-alfa))`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Superficies. Estilo de iOS: vidrio translúcido sobre el fondo, sin
        // degradés. El blur vive en index.css, sobre .bg-panel.
        fondo: color("fondo"),
        panel: translucido("panel"),
        // El vidrio de un diálogo: en claro, casi opaco, para que lo de atrás
        // no se transparente entre las líneas del mensaje. En oscuro, = panel.
        hoja: translucido("hoja"),
        borde: translucido("borde"),
        // Campos, códigos, chips grises: un hundido dentro del vidrio.
        hundido: translucido("hundido"),
        // Barras fijas (arriba y abajo) y el velo detrás de un diálogo.
        barra: translucido("barra"),
        velo: translucido("velo"),
        // Lo que se pinta al pasar el mouse o al tocar un botón de vidrio, y
        // la pestaña elegida del control segmentado.
        pulsado: translucido("pulsado"),
        elegido: translucido("elegido"),

        // Texto. `texto` es el principal (label de iOS); `tenue`, el
        // secundario (secondaryLabel).
        texto: color("texto"),
        tenue: translucido("tenue"),

        // Colores de sistema de Apple. DEFAULT para rellenos, bordes, puntos e
        // íconos. `tinta` para TEXTO chico en ese color: en claro es la
        // variante oscura de iOS, porque un verde o un naranja de sistema
        // sobre blanco no se leen; en oscuro es el mismo color.
        acento: { DEFAULT: color("acento"), tinta: color("acento-tinta") }, // systemBlue
        rojo: { DEFAULT: color("rojo"), tinta: color("rojo-tinta") }, // systemRed
        verde: { DEFAULT: color("verde"), tinta: color("verde-tinta") }, // systemGreen
        naranja: { DEFAULT: color("naranja"), tinta: color("naranja-tinta") }, // systemOrange
        // Gris azulado: lo que ya pasó pero no es un error (evento terminado).
        gris: color("gris"),

        // Los dos que NO cambian con el tema. `luz`: texto e íconos sobre un
        // relleno de color (bg-acento text-luz) o encima de una foto, y el
        // fondo del QR. `sombra`: sombras y oscurecidos encima de una foto.
        luz: color("luz"),
        sombra: color("sombra"),
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
