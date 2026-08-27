import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Para poder abrir la app del invitado desde un celular de la misma red y
    // probar la cámara de verdad, que es la única forma de probarla.
    host: true,
  },
});
