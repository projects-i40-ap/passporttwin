import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    // Los bind mounts de Docker Desktop en Windows no emiten eventos inotify.
    // Sin polling, Vite sigue sirviendo la transformación anterior de los
    // módulos aunque el fichero ya haya cambiado en disco.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
});
