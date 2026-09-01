import type { Metadata } from "next";
import { Inter, Playfair_Display } from "next/font/google";

import Provider from "./provider";
import "./globals.css";

// Self-hosted at build time -- no CDN request at runtime, so the app works
// on a firm's network without reaching out to Google.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

// Only the display weight is pulled: the serif is for case titles and
// statute headings, never body text.
const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
  weight: ["700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pramāṇa AI",
  description: "Indian legal research over primary sources.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${playfair.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
