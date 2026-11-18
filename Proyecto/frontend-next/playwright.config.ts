/**
 * Pruebas de navegador (Playwright). Hoy: la prueba de desborde horizontal en móvil
 * (tests/e2e/desborde-movil.spec.ts). No necesitan backend: tests/e2e/simulacion.ts responde
 * las llamadas al BFF.
 *
 *   npx playwright install chromium     # una vez
 *   npm run test:e2e                     # construye y levanta la app en el puerto 3100
 *
 * Con E2E_BASE_URL se usa una app que ya está corriendo (por ejemplo `npm run dev -- -p 3100`).
 */
import { defineConfig, devices } from "@playwright/test";

const PUERTO = 3100;
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${PUERTO}`;

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "movil-390", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, isMobile: false } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `npm run build && npx next start -p ${PUERTO}`,
        url: baseURL,
        timeout: 300_000,
        reuseExistingServer: !process.env.CI,
        env: { NEXT_PUBLIC_DEMO: "0", API_URL: "http://127.0.0.1:9" },
      },
});
