import Link from "next/link";
import { Nav } from "@/components/nav";
import { PageContainer } from "@/components/page-container";
import { SignOutButton } from "@/components/sign-out-button";
import { TicketProvider } from "@/components/ticket";
import { verifySession } from "@/lib/session";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await verifySession();
  return (
    <>
      <header className="sticky top-0 z-10 border-b bg-card">
        <PageContainer className="flex min-h-16 flex-wrap items-center gap-x-4 gap-y-2 py-2">
          <Link href="/dashboard" className="text-lg font-bold tracking-tight">
            Forecast desk
          </Link>
          <Nav />
          <div className="ml-auto flex items-center gap-3">
            <span
              title="Paper trading: predictions are recorded and scored. No orders are sent to Kalshi."
              className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-warn"
            >
              Paper trading
            </span>
            <span className="hidden text-sm text-muted-foreground sm:inline">{user.email}</span>
            <SignOutButton />
          </div>
        </PageContainer>
      </header>
      <main className="flex-1 pb-16 pt-10">
        <PageContainer>
          <TicketProvider>{children}</TicketProvider>
        </PageContainer>
      </main>
    </>
  );
}
