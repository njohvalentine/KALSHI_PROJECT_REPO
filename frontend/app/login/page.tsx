import { PageContainer } from "@/components/page-container";
import { PageHeader } from "@/components/page-header";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <>
      <header className="border-b bg-card">
        <PageContainer className="flex min-h-16 items-center">
          <span className="text-lg font-bold tracking-tight">Forecast desk</span>
        </PageContainer>
      </header>
      <main className="flex-1 pb-16 pt-10">
        <PageContainer>
          <PageHeader title="Sign in" description="Use the account the operator created for you." />
          <div className="max-w-sm">
            <LoginForm />
          </div>
        </PageContainer>
      </main>
    </>
  );
}
