import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { DeteccionTeclado } from "@/components/ui/DeteccionTeclado";
import { SCRIPT_TEMA } from "@/lib/tema";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});

/**
 * Mejoras 19-11 · Favicon e íconos: convención de archivos de Next.js (app/favicon.ico, app/icon*.png,
 * app/icon.svg y app/apple-icon.png). Next agrega los <link rel="icon"> y <link rel="apple-touch-icon">
 * con sus tamaños; se regeneran desde el logo con `npm run iconos` (scripts/generar-iconos.mjs).
 */
export const metadata: Metadata = {
  applicationName: "ComplianceAI · TherionLabs",
  appleWebApp: { title: "ComplianceAI" },
  title: { default: "Panel · ComplianceAI", template: "%s · ComplianceAI" },
  description: "Gobernanza de IA y cumplimiento de la Ley 21.719: madurez por dominio y brechas priorizadas.",
};

export const viewport: Viewport = {
  themeColor: "#050807",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // Corrección 18-11: SCRIPT_TEMA pone data-theme antes de pintar (lib/tema.ts); por eso <html> no coincide con
    // el HTML del servidor y se suprime ese aviso de hidratación (solo para los atributos de <html>).
    <html lang="es-CL" className={`${inter.variable} ${spaceGrotesk.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_TEMA }} />
      </head>
      <body>
        <DeteccionTeclado />
        {children}
      </body>
    </html>
  );
}
