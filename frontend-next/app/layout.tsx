import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'DerivInsight Enterprise Hub — Palantir Foundry Architecture',
  description: 'Next.js App Router full-stack e-commerce modernization platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[#090d16] text-slate-100 antialiased selection:bg-cyan-500 selection:text-black">
        {children}
      </body>
    </html>
  );
}
