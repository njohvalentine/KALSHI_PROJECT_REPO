import Link from "next/link";
import { Nav } from "@/components/nav";
import { PageContainer } from "@/components/page-container";
import { SignOutButton } from "@/components/sign-out-button";
import { verifySession } from "@/lib/session";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await verifySession();
  return (
    <>
      <header className="border-b bg-card">
        <PageContainer className="flex min-h-16 flex-wrap items-center gap-x-8 gap-y-2 py-2">
          <Link href="/games" className="text-lg font-bold tracking-tight">
            Forecast desk
          </Link>
          <Nav />
          <div className="ml-auto flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{user.email}</span>
            <SignOutButton />
          </div>
        </PageContainer>
      </header>
      <div className="border-b border-[#f1d9b6] bg-warn-soft text-sm text-warn">
        <PageContainer className="py-2">
          Paper trading: predictions are recorded and scored. No orders are sent to Kalshi.
        </PageContainer>
      </div>
      <main className="flex-1 pb-16 pt-10">
        <PageContainer>{children}</PageContainer>
      </main>
    </>
  );
}
