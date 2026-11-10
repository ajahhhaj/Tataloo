
import { defineConfig } from "vite";

export default defineConfig({
    base: "./",

    build: {
        outDir: "../app/src/main/assets/editor",
        emptyOutDir: true,
        assetsDir: "assets",
        cssCodeSplit: false,

        rollupOptions: {
            output: {
                entryFileNames: "editor.js",
                assetFileNames: "editor.[ext]"
            }
        }
    }
});
